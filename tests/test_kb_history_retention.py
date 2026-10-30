"""В43-3: сырые ответы базы знаний ФАКТ не лежат в истории чата дольше срока.

Удаляются только строки tool_use сервера ``fakt_kb`` старше срока хранения.
Строки других инструментов, текст модели и свежие строки базы остаются.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from src.claude.session import SessionManager
from src.event_bus.bus import EventBus
from src.web.message_store import MessageHistoryPersister


def _insert(sm: SessionManager, *, kind: str, name: str | None, created_at: str) -> None:
    meta = json.dumps({"name": name}) if name else None
    conn = sm._get_connection()
    with sm._conn_lock:
        conn.execute(
            "INSERT INTO messages (topic_id, request_id, type, kind, content, metadata_json, "
            "created_at) VALUES (1, 'r', 'streaming_update', ?, 'x', ?, ?)",
            (kind, meta, created_at),
        )
        conn.commit()


def _count(sm: SessionManager) -> int:
    return sm._get_connection().execute("SELECT COUNT(*) FROM messages").fetchone()[0]


def _stamp(days_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


def test_old_kb_tool_rows_are_purged_and_others_kept(tmp_path) -> None:
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    sm.create_session(topic_id=1, project_path=str(tmp_path), project_name="p")
    _insert(sm, kind="tool_use", name="mcp__fakt_kb__search_project", created_at=_stamp(40))
    _insert(sm, kind="tool_use", name="mcp__fakt_kb__get_fragment", created_at=_stamp(1))
    _insert(sm, kind="tool_use", name="Read", created_at=_stamp(40))
    _insert(sm, kind="text", name=None, created_at=_stamp(40))
    persister = MessageHistoryPersister(
        bus=EventBus(), session_manager=sm, kb_tool_retention_days=30
    )
    try:
        assert persister.purge_kb_tool_rows() == 1
        assert _count(sm) == 3
        assert persister.purge_kb_tool_rows() == 0
    finally:
        sm.close_sync()


def test_zero_days_disables_purge(tmp_path) -> None:
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    sm.create_session(topic_id=1, project_path=str(tmp_path), project_name="p")
    _insert(sm, kind="tool_use", name="mcp__fakt_kb__search_project", created_at=_stamp(400))
    persister = MessageHistoryPersister(
        bus=EventBus(), session_manager=sm, kb_tool_retention_days=0
    )
    try:
        assert persister.purge_kb_tool_rows() == 0
        assert _count(sm) == 1
    finally:
        sm.close_sync()
