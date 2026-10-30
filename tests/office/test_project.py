"""Паспорт проекта офиса через /api/office (граница project, таск 02).

Роутер на временной SQLite: паспорт, предложение типа, черновик без типа,
идемпотентное создание, листание списка, запрет смены типа после принятого
задания, создатель-менеджер и отказ на чужой проект.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.web.passwords import hash_password
from src.web.server import WebServer

# Тестовый пароль локальных аккаунтов, не секрет.
_PASSWORD = "test-only-password"

_PASSPORT = {
    "name": "Сайт пекарни",
    "work_kind": "site",
    "nature": "custom",
    "description": "Лендинг с меню и формой заказа",
}


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


@asynccontextmanager
async def _client_as(srv: WebServer, username: str):
    async with AsyncClient(
        transport=ASGITransport(app=srv.app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/api/auth/login", json={"username": username, "password": _PASSWORD}
        )
        assert r.status_code == 200
        yield client


@pytest.mark.asyncio
async def test_passport_keeps_work_kind_and_nature_separately(server) -> None:
    srv, sm = server
    _user(sm, "pm")
    async with _client_as(srv, "pm") as c:
        r = await c.post("/api/office/projects", json=_PASSPORT)
        assert r.status_code == 201
        created = r.json()
        got = (await c.get(f"/api/office/projects/{created['id']}")).json()
    assert got["work_kind"] == "site"
    assert got["nature"] == "custom"
    assert got["description"] == "Лендинг с меню и формой заказа"


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["work_kind", "nature", "name"])
async def test_passport_requires_work_kind_and_nature(server, missing) -> None:
    srv, sm = server
    _user(sm, "pm")
    body = {k: v for k, v in _PASSPORT.items() if k != missing}
    async with _client_as(srv, "pm") as c:
        r = await c.post("/api/office/projects", json=body)
        listed = (await c.get("/api/office/projects")).json()
    assert r.status_code == 422
    assert listed == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("work_kind", "nature", "expected"),
    [
        ("site", "custom", "small"),
        ("mobile_app", "product", "large"),
        ("web_platform", "custom", "large"),
    ],
)
async def test_platform_suggests_type_with_one_sentence(
    server, work_kind, nature, expected
) -> None:
    srv, sm = server
    _user(sm, "pm")
    async with _client_as(srv, "pm") as c:
        r = await c.post(
            "/api/office/type-suggestion",
            json={"work_kind": work_kind, "nature": nature, "description": ""},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["project_type"] == expected
    reason = body["reason"].strip()
    # Одна фраза: непустая, одна точка в конце.
    assert reason and reason.endswith(".") and reason.count(".") == 1


@pytest.mark.asyncio
async def test_project_without_type_stays_draft_until_manager_chooses(server) -> None:
    srv, sm = server
    _user(sm, "pm")
    async with _client_as(srv, "pm") as c:
        created = (await c.post("/api/office/projects", json=_PASSPORT)).json()
        assert created["project_type"] == ""
        assert created["status"] == "draft"
        r = await c.put(
            f"/api/office/projects/{created['id']}/type", json={"project_type": "small"}
        )
        assert r.status_code == 200
        got = (await c.get(f"/api/office/projects/{created['id']}")).json()
    assert got["project_type"] == "small"
    assert got["status"] == "active"


@pytest.mark.asyncio
async def test_type_chosen_in_wizard_starts_project(server) -> None:
    srv, sm = server
    _user(sm, "pm")
    async with _client_as(srv, "pm") as c:
        r = await c.post(
            "/api/office/projects", json={**_PASSPORT, "project_type": "large"}
        )
        bad = await c.post("/api/office/projects", json={**_PASSPORT, "project_type": "huge"})
    assert r.json()["project_type"] == "large"
    assert r.json()["status"] == "active"
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_double_create_with_same_key_makes_one_project(server) -> None:
    srv, sm = server
    _user(sm, "pm")
    body = {**_PASSPORT, "request_key": "draft-7f3a"}
    async with _client_as(srv, "pm") as c:
        first = await c.post("/api/office/projects", json=body)
        second = await c.post("/api/office/projects", json=body)
        other = await c.post(
            "/api/office/projects", json={**_PASSPORT, "request_key": "draft-other"}
        )
        listed = (await c.get("/api/office/projects")).json()
    assert first.json()["id"] == second.json()["id"]
    assert other.json()["id"] != first.json()["id"]
    assert len(listed) == 2


@pytest.mark.asyncio
async def test_project_list_is_paged(server) -> None:
    srv, sm = server
    _user(sm, "pm")
    async with _client_as(srv, "pm") as c:
        for n in range(5):
            await c.post("/api/office/projects", json={**_PASSPORT, "name": f"П{n}"})
        first = (await c.get("/api/office/projects?limit=2")).json()
        second = (await c.get("/api/office/projects?limit=2&offset=2")).json()
        last = (await c.get("/api/office/projects?limit=2&offset=4")).json()
        too_big = await c.get("/api/office/projects?limit=100000")
    assert [p["name"] for p in first] == ["П0", "П1"]
    assert [p["name"] for p in second] == ["П2", "П3"]
    assert [p["name"] for p in last] == ["П4"]
    assert too_big.status_code == 422


@pytest.mark.asyncio
async def test_type_locked_once_spec_version_accepted(server) -> None:
    srv, sm = server
    _user(sm, "pm")
    async with _client_as(srv, "pm") as c:
        created = (
            await c.post("/api/office/projects", json={**_PASSPORT, "project_type": "small"})
        ).json()
        pid = created["id"]
        # Задание есть, но версия ещё не принята: тип менять можно.
        store = srv.office_store
        spec = store.ensure_document(pid, "spec")
        v1 = store.add_version(spec["id"], markdown="# ТЗ", source="test")
        free = await c.put(f"/api/office/projects/{pid}/type", json={"project_type": "large"})
        # Заказчик принял версию задания: проверка идёт по версиям.
        store.set_version_status(v1["id"], "accepted")
        store.add_version(spec["id"], markdown="# ТЗ v2", source="test")
        locked = await c.put(f"/api/office/projects/{pid}/type", json={"project_type": "small"})
        got = (await c.get(f"/api/office/projects/{pid}")).json()
    assert free.status_code == 200
    assert locked.status_code == 409
    assert locked.json()["detail"]
    assert got["project_type"] == "large"


@pytest.mark.asyncio
async def test_creator_is_manager_and_foreign_project_is_refused(server) -> None:
    srv, sm = server
    pm = _user(sm, "pm")
    _user(sm, "stranger")
    dev = _user(sm, "dev")
    async with _client_as(srv, "pm") as c:
        pid = (await c.post("/api/office/projects", json=_PASSPORT)).json()["id"]
    assert srv.office_store.get_member(pid, pm)["role"] == "project_manager"
    srv.office_store.add_member(pid, dev, "developer")
    async with _client_as(srv, "stranger") as c:
        foreign_get = await c.get(f"/api/office/projects/{pid}")
        foreign_put = await c.put(
            f"/api/office/projects/{pid}/type", json={"project_type": "small"}
        )
    async with _client_as(srv, "dev") as c:
        member_put = await c.put(
            f"/api/office/projects/{pid}/type", json={"project_type": "small"}
        )
    assert foreign_get.status_code == 404
    assert foreign_put.status_code == 404
    assert member_put.status_code == 403
    assert srv.office_store.get_project(pid)["project_type"] == ""
