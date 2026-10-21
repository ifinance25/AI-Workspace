"""Доступ к проектам офиса через /api/office.

Чужой проект отдаёт отказ, не пустое тело; администратор видит все проекты;
без входа 401, как у остальных маршрутов приложения.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.office import tenancy
from src.web.passwords import hash_password
from src.web.server import WebServer

# Тестовый пароль локальных аккаунтов, не секрет.
_PASSWORD = "test-only-password"


@pytest.fixture
def server(tmp_path):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    settings = WebSettings(
        enabled=True, host="127.0.0.1", port=0, jwt_secret="x" * 32,
        telegram_bot_username="t",
    )
    srv = WebServer(
        settings=settings,
        allowed_user_ids=[],
        bot_username="t",
        session_manager=sm,
        event_bus=EventBus(),
        jwt_secret="x" * 32,
    )
    try:
        yield srv, sm
    finally:
        srv.office_store.close()
        sm.close_sync()
        sm._engine.sync_engine.dispose()


def _user(sm: SessionManager, username: str, *, is_admin: bool = False) -> int:
    return sm.create_local_user(
        username=username, password_hash=hash_password(_PASSWORD), is_admin=is_admin
    )


def _client(srv: WebServer) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=srv.app), base_url="http://test")


async def _login(client: AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/auth/login", json={"username": username, "password": _PASSWORD}
    )
    assert r.status_code == 200


def _two_projects(srv: WebServer, u1: int, u2: int) -> tuple[int, int]:
    store = srv.office_store
    p1 = store.create_project(name="Лендинг", created_by=u1)
    tenancy.record_creator(store, p1["id"], u1)
    p2 = store.create_project(name="Чат-бот", created_by=u2)
    tenancy.record_creator(store, p2["id"], u2)
    return p1["id"], p2["id"]


async def test_without_login_is_401(server) -> None:
    srv, _ = server
    async with _client(srv) as client:
        r = await client.get("/api/office/projects")
    assert r.status_code == 401


async def test_member_sees_own_projects_and_foreign_is_refused(server) -> None:
    srv, sm = server
    u1, u2 = _user(sm, "u1"), _user(sm, "u2")
    p1, p2 = _two_projects(srv, u1, u2)
    async with _client(srv) as client:
        await _login(client, "u1")
        listed = await client.get("/api/office/projects")
        own = await client.get(f"/api/office/projects/{p1}")
        foreign = await client.get(f"/api/office/projects/{p2}")
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [p1]
    assert own.status_code == 200
    assert own.json()["name"] == "Лендинг"
    assert foreign.status_code in (403, 404)
    assert foreign.json()["detail"]


async def test_missing_project_is_404_with_detail(server) -> None:
    srv, sm = server
    u1, u2 = _user(sm, "u1"), _user(sm, "u2")
    _, p2 = _two_projects(srv, u1, u2)
    async with _client(srv) as client:
        await _login(client, "u1")
        r = await client.get(f"/api/office/projects/{p2 + 1000}")
    assert r.status_code == 404
    assert r.json()["detail"] == "Проект не найден"


async def test_creator_is_recorded_as_project_manager(server) -> None:
    srv, sm = server
    u1, u2 = _user(sm, "u1"), _user(sm, "u2")
    p1, _ = _two_projects(srv, u1, u2)
    members = srv.office_store.list_members(p1)
    assert [(m["user_id"], m["role"]) for m in members] == [(u1, "project_manager")]
    assert tenancy.ROLES["project_manager"] == "Менеджер проекта"


async def test_admin_sees_all_projects(server) -> None:
    srv, sm = server
    u1, u2 = _user(sm, "u1"), _user(sm, "u2")
    _user(sm, "root", is_admin=True)
    p1, p2 = _two_projects(srv, u1, u2)
    async with _client(srv) as client:
        await _login(client, "root")
        listed = await client.get("/api/office/projects")
        foreign = await client.get(f"/api/office/projects/{p2}")
    assert [p["id"] for p in listed.json()] == [p1, p2]
    assert foreign.status_code == 200
