"""Файлы прогона рядом с базой. Запись атомарная, файлы всегда собираются из базы."""
from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from typing import Any

import structlog

from src.office.delivery._validation_render import (
    journal_line,
    render_finding,
    render_summary,
)
from src.office.delivery._validation_schema import ValidationError, data_root, ensure, run_dir
from src.office.delivery._validation_stats import run_stats

log = structlog.get_logger()
_write_lock = threading.Lock()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _run(conn: Any, project_id: int, run_id: int) -> Any:
    run = conn.execute(
        "SELECT * FROM office_validation_runs WHERE id = ? AND project_id = ?",
        (run_id, project_id),
    ).fetchone()
    if run is None:
        raise ValidationError("not_found", "Прогон не найден")
    return run


def _render_rows(conn: Any, run: Any, row: Any) -> str:
    edits = conn.execute(
        "SELECT * FROM office_validation_edits WHERE finding_id = ? ORDER BY ordinal", (row["id"],)
    ).fetchall()
    decisions = conn.execute(
        "SELECT * FROM office_validation_decisions WHERE finding_id = ? ORDER BY seq", (row["id"],)
    ).fetchall()
    return render_finding(run, row, edits, decisions)


def _write_run(conn: Any, store: Any, run: Any, stale: list) -> None:
    root = run_dir(store, run["project_id"], run["id"])
    for row in stale:
        _atomic_write(root / "findings" / f"{row['gid']}.md", _render_rows(conn, run, row))
    gids = dict(conn.execute(
        "SELECT id, gid FROM office_validation_findings WHERE run_id = ?", (run["id"],)
    ).fetchall())
    rows = conn.execute(
        "SELECT * FROM office_validation_decisions WHERE run_id = ? ORDER BY id", (run["id"],)
    ).fetchall()
    journal = "".join(journal_line(run, gids[r["finding_id"]], r) + "\n" for r in rows)
    _atomic_write(root / "journal.jsonl", journal)
    _atomic_write(root / "summary.md", render_summary(run, run_stats(conn, run["id"])))


def sync_files(store: Any, project_id: int, run_id: int, *, force: bool = False) -> bool:
    """Догнать файлы до базы. ``False``: файл не записан, решение остаётся в базе."""
    ensure(store)
    with _write_lock, store._lock:
        conn = store._connection()
        run = _run(conn, project_id, run_id)
        condition = "" if force else "AND rendered_seq != decision_seq"
        stale = conn.execute(
            f"SELECT * FROM office_validation_findings WHERE run_id = ? {condition}", (run_id,)
        ).fetchall()
        if not stale:
            return True
        try:
            _write_run(conn, store, run, stale)
        except OSError as exc:
            log.warning("validation_files_stale", run_id=run_id, error=type(exc).__name__)
            return False
        conn.executemany(
            "UPDATE office_validation_findings SET rendered_seq = ? WHERE id = ?",
            [(r["decision_seq"], r["id"]) for r in stale],
        )
        conn.commit()
    return True


def rebuild_files(store: Any, project_id: int, run_id: int) -> bool:
    """Собрать все файлы заново, например после восстановления копии базы."""
    return sync_files(store, project_id, run_id, force=True)


def purge_project_files(store: Any, project_id: int) -> None:
    shutil.rmtree(data_root(store) / f"p{int(project_id)}", ignore_errors=True)
