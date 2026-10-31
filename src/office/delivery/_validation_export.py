"""Выгрузка для внешней модели: только markdown и журнал, без снимков и PDF (28 §4.2)."""
from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import datetime, timezone
from typing import Any

from src.office.delivery._scan import scan
from src.office.delivery._validation_files import _run, sync_files
from src.office.delivery._validation_read import get_policy
from src.office.delivery._validation_schema import ValidationError, ensure, run_dir

_EPOCH = (1980, 1, 1, 0, 0, 0)


def _collect(store: Any, project_id: int, run_id: int) -> list[tuple[str, bytes]]:
    root = run_dir(store, project_id, run_id)
    names = sorted(root.glob("findings/*.md")) + [root / "journal.jsonl", root / "summary.md"]
    return [(str(p.relative_to(root)), p.read_bytes()) for p in names if p.is_file()]


def export_run(store: Any, project_id: int, run_id: int, *, actor_id: int) -> tuple[bytes, str]:
    """Архив и его имя. Вывод закрыт, пока МП его не разрешил."""
    ensure(store)
    if get_policy(store, project_id) != "none":
        raise ValidationError("export_banned", "Вывоз данных не разрешён менеджером проекта")
    if not sync_files(store, project_id, run_id):
        raise ValidationError("files_stale", "Файлы прогона не удалось обновить")
    files = _collect(store, project_id, run_id)
    hits = sorted({h for _, body in files for h in scan(body.decode("utf-8"))})
    if hits:
        raise ValidationError("scan_failed", f"Сканер остановил выгрузку: {', '.join(hits)}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in files:
            archive.writestr(zipfile.ZipInfo(name, date_time=_EPOCH), body)
    data = buffer.getvalue()
    with store._lock:
        conn = store._connection()
        run = _run(conn, project_id, run_id)
        conn.execute(
            "INSERT INTO office_validation_exports (run_id, actor_id, at, sha256, files) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, actor_id, datetime.now(timezone.utc).isoformat(timespec="seconds"),
             hashlib.sha256(data).hexdigest(), len(files)),
        )
        conn.commit()
    return data, f"{run['run_key']}-markdown.zip"
