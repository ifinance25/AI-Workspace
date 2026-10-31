"""Режим только офиса: роутеры файлов, загрузок, терминала, WebSocket закрыты."""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.web.passwords import hash_password
from src.web.server import WebServer

_PASSWORD = "test-only-password"
_SECRET = "x" * 32
_CLOSED = [
    ("GET", "/api/files/tree"),
    ("GET", "/api/files/artifacts"),
    ("GET", "/api/ssh"),
]
_OPEN = [("GET", "/api/office/projects"), ("GET", "/api/health")]


def _server(tmp_path, *, office_only: bool):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    settings = WebSettings(
        enabled=True, host="127.0.0.1", port=0, jwt_secret=_SECRET, telegram_bot_username="t"
    )
    srv = WebServer(
        settings=settings, allowed_user_ids=[], bot_username="t", session_manager=sm,
        event_bus=EventBus(), jwt_secret=_SECRET, office_only=office_only,
    )
    return srv, sm


@asynccontextmanager
async def _running(tmp_path, *, office_only: bool):
    srv, sm = _server(tmp_path, office_only=office_only)
    sm.create_local_user(username="lead", password_hash=hash_password(_PASSWORD), is_admin=True)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=srv.app), base_url="http://test"
        ) as client:
            r = await client.post(
                "/api/auth/login", json={"username": "lead", "password": _PASSWORD}
            )
            assert r.status_code == 200
            yield client
    finally:
        srv.office_store.close()
        sm.close_sync()
        sm._engine.sync_engine.dispose()


@pytest.mark.parametrize("method,path", _CLOSED)
async def test_default_mode_keeps_routes(tmp_path, method, path):
    async with _running(tmp_path, office_only=False) as client:
        response = await client.request(method, path)
    assert response.status_code != 404, (method, path)


@pytest.mark.parametrize("method,path", _CLOSED)
async def test_office_only_closes_routes_even_for_admin(tmp_path, method, path):
    async with _running(tmp_path, office_only=True) as client:
        response = await client.request(method, path)
    assert response.status_code == 404, (method, path, response.status_code)


async def test_uploads_route_exists_only_in_default_mode(tmp_path):
    async with _running(tmp_path, office_only=False) as client:
        kept = await client.post("/api/uploads")
    async with _running(tmp_path / "second", office_only=True) as client:
        closed = await client.post("/api/uploads")
    assert kept.status_code not in (404, 405)
    assert closed.status_code in (404, 405)


async def test_unknown_api_path_is_404_not_frontend_page(tmp_path):
    async with _running(tmp_path, office_only=False) as client:
        response = await client.get("/api/no-such-endpoint")
    assert response.status_code == 404
    assert "<html" not in response.text.lower()


@pytest.mark.parametrize("method,path", _OPEN)
async def test_office_only_keeps_office_and_health(tmp_path, method, path):
    async with _running(tmp_path, office_only=True) as client:
        response = await client.request(method, path)
    assert response.status_code == 200, (method, path, response.status_code)


async def test_office_only_has_no_websocket_forwarder_routes(tmp_path):
    srv, sm = _server(tmp_path, office_only=True)
    try:
        paths = []
        for route in srv.app.router.routes:
            paths.append(getattr(route, "path", ""))
        assert not any(p.startswith("/api/ws") for p in paths)
    finally:
        srv.office_store.close()
        sm.close_sync()
        sm._engine.sync_engine.dispose()
