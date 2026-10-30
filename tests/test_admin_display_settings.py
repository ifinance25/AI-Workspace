"""GET/PATCH /api/admin/display и show_token_usage в GET /api/me."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import DisplaySettings, WebSettings
from src.event_bus.bus import EventBus
from src.web.passwords import hash_password
from src.web.server import WebServer

pytestmark = pytest.mark.asyncio


@pytest.fixture
def setup():
    tmp = Path(tempfile.mkdtemp())
    bus = EventBus()
    sm = SessionManager(storage_path=tmp / "sessions.db")
    sm.create_local_user(
        username="admin", password_hash=hash_password("pw1234567890"), is_admin=True
    )
    sm.create_local_user(
        username="user", password_hash=hash_password("pw1234567890"), is_admin=False
    )
    display = DisplaySettings(show_token_usage=True)
    server = WebServer(
        settings=WebSettings(
            enabled=True, host="127.0.0.1", port=0, jwt_secret="x" * 32
        ),
        allowed_user_ids=[100],
        bot_username="t",
        session_manager=sm,
        event_bus=bus,
        bot_token="12345:abc",
        jwt_secret="x" * 32,
        project_paths=[tmp],
        display_settings=display,
    )
    try:
        yield server, display
    finally:
        sm.close_sync()
        sm._engine.sync_engine.dispose()
        shutil.rmtree(tmp, ignore_errors=True)


async def test_me_reflects_show_token_usage(setup):
    server, display = setup
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/auth/login", json={"username": "user", "password": "pw1234567890"}
        )
        me = await client.get("/api/me")
        assert me.status_code == 200
        assert me.json()["show_token_usage"] is True

        display.show_token_usage = False
        me2 = await client.get("/api/me")
        assert me2.json()["show_token_usage"] is False


async def test_admin_patch_display_updates_me(setup):
    server, _display = setup
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/auth/login", json={"username": "admin", "password": "pw1234567890"}
        )
        r = await client.patch("/api/admin/display", json={"show_token_usage": False})
        assert r.status_code == 200
        assert r.json()["show_token_usage"] is False

        me = await client.get("/api/me")
        assert me.json()["show_token_usage"] is False


async def test_non_admin_cannot_patch_display(setup):
    server, _display = setup
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/auth/login", json={"username": "user", "password": "pw1234567890"}
        )
        r = await client.patch("/api/admin/display", json={"show_token_usage": False})
        assert r.status_code == 403
