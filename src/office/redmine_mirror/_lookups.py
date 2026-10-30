"""Справочники формы задач Redmine (из kanban-дашборда), хранятся в SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOOKUPS_ID = 1
_FIXTURE_REL = Path("data/fixtures/redmine_kanban_lookups.json")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS office_redmine_lookups (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_fixture_path() -> Path:
    return repo_root() / _FIXTURE_REL


def _ensure(store: Any) -> None:
    with store._lock:
        conn = store._connection()
        conn.executescript(_SCHEMA)
        conn.commit()


def _iso(moment: datetime | None = None) -> str:
    when = moment or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).isoformat(timespec="seconds")


def load_lookups(store: Any) -> dict | None:
    """Полный JSON фикстуры из БД или None."""
    _ensure(store)
    with store._lock:
        row = store._connection().execute(
            "SELECT payload FROM office_redmine_lookups WHERE id = ?",
            (_LOOKUPS_ID,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["payload"])


def filters_for_api(store: Any) -> dict | None:
    data = load_lookups(store)
    if not data:
        return None
    filters = data.get("filters")
    if not isinstance(filters, dict):
        return None
    people = data.get("people_by_name")
    if isinstance(people, dict):
        return {**filters, "people_by_name": people}
    return dict(filters)


def seed_lookups(store: Any, *, fixture_path: Path | None = None) -> dict:
    """Записать справочники из JSON-файла в БД (перезаписывает строку id=1)."""
    path = fixture_path or default_fixture_path()
    if not path.is_file():
        raise FileNotFoundError(f"Фикстура справочников не найдена: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("filters"), dict):
        raise ValueError("В фикстуре нет объекта filters")
    _ensure(store)
    blob = json.dumps(payload, ensure_ascii=False)
    with store._lock:
        conn = store._connection()
        conn.execute(
            "INSERT INTO office_redmine_lookups (id, payload, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, "
            "updated_at = excluded.updated_at",
            (_LOOKUPS_ID, blob, _iso()),
        )
        conn.commit()
    return payload
