"""GET /api/version: за входом, отдаёт коммит и время запуска."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.web.passwords import hash_password
from src.web.server import WebServer

_PASSWORD = "test-only-password"


@pytest.fixture
def server(tmp_path):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    settings = WebSettings(
        enabled=True, host="127.0.0.1", port=0, jwt_secret="x" * 32, telegram_bot_username="t"
    )
    srv = WebServer(
        settings=settings, allowed_user_ids=[], bot_username="t", session_manager=sm,
        event_bus=EventBus(), jwt_secret="x" * 32,
    )
    sm.create_local_user(username="ivan", password_hash=hash_password(_PASSWORD), is_admin=False)
    try:
        yield srv
    finally:
        if srv.office_store is not None:
            srv.office_store.close()
        sm.close_sync()
        sm._engine.sync_engine.dispose()


async def test_version_needs_login_and_has_commit(server) -> None:
    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://test") as c:
        assert (await c.get("/api/version")).status_code == 401
        login = await c.post("/api/auth/login", json={"username": "ivan", "password": _PASSWORD})
        assert login.status_code == 200
        body = (await c.get("/api/version")).json()
        assert body["commit"]
        assert body["started_at"].endswith("+00:00")
