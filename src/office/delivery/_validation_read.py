"""Чтение прогонов для экрана. Каждый запрос ограничен проектом."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.office.delivery._validation_files import _run, sync_files
from src.office.delivery._validation_schema import ValidationError, ensure, run_dir
from src.office.delivery._validation_stats import run_stats

_FOLDERS = {"image": "img", "pdf": "docs"}
_POLICY_VALUES = frozenset({"none", "all_external"})
SUMMARY_PREVIEW = 220


def _conn(store: Any) -> Any:
    ensure(store)
    return store._connection()


def list_runs(store: Any, project_id: int) -> list[dict]:
    with store._lock:
        rows = _conn(store).execute(
            "SELECT id, run_key, source_kind, title, stand_version, imported_at FROM "
            "office_validation_runs WHERE project_id = ? ORDER BY id DESC", (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def has_runs(store: Any, project_id: int) -> bool:
    return bool(list_runs(store, project_id))


def get_run(store: Any, project_id: int, run_id: int) -> dict:
    with store._lock:
        conn = _conn(store)
        run = _run(conn, project_id, run_id)
        docs = conn.execute(
            "SELECT id, name FROM office_validation_assets WHERE run_id = ? AND kind = 'pdf' "
            "ORDER BY name", (run_id,)
        ).fetchall()
        stats = run_stats(conn, run_id)
    keys = ("id", "run_key", "source_kind", "title", "stand_version", "imported_at")
    return {**{k: run[k] for k in keys}, "docs": [dict(d) for d in docs], "stats": stats}


def list_findings(store: Any, project_id: int, run_id: int) -> list[dict]:
    """Список карточек. Заодно чинит файлы, отставшие после сбоя записи."""
    sync_files(store, project_id, run_id)
    with store._lock:
        rows = _conn(store).execute(
            "SELECT id, gid, doc, category, defect_class, severity_raw, llm_verdict, review_status, "
            "lifecycle, decision_seq, payload FROM office_validation_findings "
            "WHERE run_id = ? AND project_id = ? ORDER BY id", (run_id, project_id)
        ).fetchall()
    return [_card(r) for r in rows]


def _card(row: Any) -> dict:
    """Строка списка: без полного текста, с коротким началом сути для поиска глазами."""
    payload = json.loads(row["payload"])
    card = {k: row[k] for k in row.keys() if k != "payload"}
    return {
        **card,
        "section": payload.get("section") or "",
        "summary": str(payload.get("summary") or "")[:SUMMARY_PREVIEW],
    }


def _with_assets(entries: list, images: dict) -> list:
    return [{**e, "asset_id": images.get(e.get("img"))} for e in entries]


def get_finding(store: Any, project_id: int, run_id: int, finding_id: int) -> dict:
    with store._lock:
        conn = _conn(store)
        row = conn.execute(
            "SELECT * FROM office_validation_findings "
            "WHERE id = ? AND run_id = ? AND project_id = ?",
            (finding_id, run_id, project_id),
        ).fetchone()
        if row is None:
            raise ValidationError("not_found", "Находка не найдена")
        images = dict(conn.execute(
            "SELECT name, id FROM office_validation_assets WHERE run_id = ? AND kind = 'image'",
            (run_id,),
        ).fetchall())
        edits = conn.execute(
            "SELECT ordinal, edit_key, doc, col, place, old_text, new_text, comment, state, "
            "doc_ref "
            "FROM office_validation_edits WHERE finding_id = ? ORDER BY ordinal", (finding_id,)
        ).fetchall()
        history = conn.execute(
            "SELECT seq, decision_key, action, review_to, lifecycle_to, reason_code, why, "
            "actor_id, actor_role, at FROM office_validation_decisions "
            "WHERE finding_id = ? ORDER BY seq",
            (finding_id,),
        ).fetchall()
    payload = json.loads(row["payload"])
    return {
        "id": row["id"], "gid": row["gid"], "doc": row["doc"], "category": row["category"],
        "defect_class": row["defect_class"],
        "severity_raw": row["severity_raw"], "llm_verdict": row["llm_verdict"],
        "llm_verdict_reason": row["llm_verdict_reason"], "review_status": row["review_status"],
        "lifecycle": row["lifecycle"], "decision_seq": row["decision_seq"],
        "summary": payload.get("summary", ""), "why": payload.get("why") or "",
        "clauses": payload.get("clauses") or [], "scenarios": payload.get("scenarios") or [],
        "redmine": payload.get("redmine") or [],
        "redmine_links": payload.get("redmine_links") or [],
        "refs": payload.get("refs") or [],
        "section": payload.get("section") or "",
        "evidence": _with_assets(payload.get("evidence") or [], images),
        "marked": _with_assets(payload.get("marked") or [], images),
        "edits": [dict(e) for e in edits], "history": [dict(h) for h in history],
    }


def asset_path(store: Any, project_id: int, run_id: int, asset_id: int) -> tuple[Path, str, str]:
    """Путь строится из чисел и имени из базы; клиент путь не передаёт."""
    with store._lock:
        conn = _conn(store)
        _run(conn, project_id, run_id)
        row = conn.execute(
            "SELECT kind, name, mime FROM office_validation_assets WHERE id = ? AND run_id = ?",
            (asset_id, run_id),
        ).fetchone()
    if row is None:
        raise ValidationError("not_found", "Файл не найден")
    root = run_dir(store, project_id, run_id).resolve()
    path = root / _FOLDERS[row["kind"]] / row["name"]
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValidationError("not_found", "Файл не найден")
    return path, row["name"], row["mime"]


def get_policy(store: Any, project_id: int) -> str:
    with store._lock:
        row = _conn(store).execute(
            "SELECT export_ban FROM office_validation_policy WHERE project_id = ?", (project_id,)
        ).fetchone()
    return row["export_ban"] if row else "all_external"


def set_policy(store: Any, project_id: int, value: str, *, actor_id: int, at: str) -> str:
    if value not in _POLICY_VALUES:
        raise ValidationError("bad_input", "Неизвестное значение")
    with store._lock:
        conn = _conn(store)
        conn.execute(
            "INSERT INTO office_validation_policy (project_id, export_ban, updated_by, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (project_id) DO UPDATE SET "
            "export_ban = excluded.export_ban, updated_by = excluded.updated_by, "
            "updated_at = excluded.updated_at",
            (project_id, value, actor_id, at),
        )
        conn.commit()
    return value
