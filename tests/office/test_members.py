"""Состав команды проекта: кто смотрит, кто меняет, проект не остаётся без менеджера."""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.office import tenancy
from src.web.passwords import hash_password
from src.web.server import WebServer

_PASSWORD = "test-only-password"
_SECRET = "x" * 32


@pytest.fixture
def server(tmp_path):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    settings = WebSettings(
        enabled=True, host="127.0.0.1", port=0, jwt_secret=_SECRET, telegram_bot_username="t"
    )
    srv = WebServer(
        settings=settings, allowed_user_ids=[], bot_username="t", session_manager=sm,
        event_bus=EventBus(), jwt_secret=_SECRET,
    )
    try:
        yield srv, sm
    finally:
        srv.office_store.close()
        sm.close_sync()
        sm._engine.sync_engine.dispose()


@asynccontextmanager
async def _client(srv, username):
    async with AsyncClient(transport=ASGITransport(app=srv.app), base_url="http://test") as client:
        r = await client.post("/api/auth/login", json={"username": username, "password": _PASSWORD})
        assert r.status_code == 200
        yield client


def _user(sm, name, *, is_admin=False) -> int:
    return sm.create_local_user(
        username=name, password_hash=hash_password(_PASSWORD), is_admin=is_admin
    )


def _setup(srv, sm) -> dict:
    office = srv.office_store
    lead = _user(sm, "lead")
    pid = office.create_project(name="Факт", created_by=lead)["id"]
    tenancy.record_creator(office, pid, lead)
    ids = {"lead": lead, "pid": pid}
    for name, role in {
        "tester": "tester", "dev": "developer", "client": "customer_representative",
    }.items():
        ids[name] = _user(sm, name)
        office.add_member(pid, ids[name], role)
    other = _user(sm, "other")
    other_project = office.create_project(name="Чужой", created_by=other)
    tenancy.record_creator(office, other_project["id"], other)
    ids["newbie"] = _user(sm, "newbie")
    _user(sm, "root", is_admin=True)
    return ids


def _url(ids) -> str:
    return f"/api/office/projects/{ids['pid']}/members"


@pytest.mark.parametrize("user,code", [
    ("lead", 200), ("root", 200), ("tester", 200), ("dev", 200),
    ("client", 403), ("other", 404),
])
async def test_who_sees_team(server, user, code):
    srv, sm = server
    ids = _setup(srv, sm)
    async with _client(srv, user) as client:
        response = await client.get(_url(ids))
    assert response.status_code == code
    if code == 200:
        body = response.json()
        assert {m["username"] for m in body["members"]} >= {"lead", "tester"}
        assert "system_admin" not in {r["key"] for r in body["roles"]}
        assert body["can_manage"] is (user in {"lead", "root"})


@pytest.mark.parametrize("user,code", [
    ("lead", 201), ("root", 201), ("tester", 403), ("dev", 403), ("client", 403), ("other", 404),
])
async def test_who_adds(server, user, code):
    srv, sm = server
    ids = _setup(srv, sm)
    async with _client(srv, user) as client:
        response = await client.post(
            _url(ids), json={"username": "newbie", "role": "business_analyst"}
        )
    assert response.status_code == code
    member = srv.office_store.get_member(ids["pid"], ids["newbie"])
    assert (member is not None) is (code == 201)


async def test_bad_role_unknown_user_and_inactive(server):
    srv, sm = server
    ids = _setup(srv, sm)
    async with _client(srv, "lead") as client:
        for role in ("system_admin", "king", ""):
            r = await client.post(_url(ids), json={"username": "newbie", "role": role})
            assert r.status_code == 422
        r = await client.post(_url(ids), json={"username": "nobody", "role": "tester"})
        assert r.status_code == 404
        assert srv.office_store.get_member(ids["pid"], ids["newbie"]) is None


async def test_change_and_remove(server):
    srv, sm = server
    ids = _setup(srv, sm)
    async with _client(srv, "lead") as client:
        r = await client.put(f"{_url(ids)}/{ids['dev']}", json={"role": "tester"})
        assert r.status_code == 200
        assert srv.office_store.get_member(ids["pid"], ids["dev"])["role"] == "tester"
        assert (await client.delete(f"{_url(ids)}/{ids['dev']}")).status_code == 204
        assert srv.office_store.get_member(ids["pid"], ids["dev"]) is None
        assert (await client.delete(f"{_url(ids)}/{ids['dev']}")).status_code == 404
        r = await client.put(f"{_url(ids)}/{ids['newbie']}", json={"role": "tester"})
        assert r.status_code == 404


async def test_last_manager_stays(server):
    srv, sm = server
    ids = _setup(srv, sm)
    async with _client(srv, "lead") as client:
        assert (await client.put(
            f"{_url(ids)}/{ids['lead']}", json={"role": "tester"}
        )).status_code == 409
        assert (await client.delete(f"{_url(ids)}/{ids['lead']}")).status_code == 409
        assert srv.office_store.get_member(ids["pid"], ids["lead"])["role"] == "project_manager"
        # второй менеджер: первый может уйти
        await client.put(f"{_url(ids)}/{ids['tester']}", json={"role": "project_manager"})
        assert (await client.delete(f"{_url(ids)}/{ids['lead']}")).status_code == 204


async def test_other_project_user_is_not_touched(server):
    srv, sm = server
    ids = _setup(srv, sm)
    other_id = sm.get_user_by_username("other")["user_id"]
    async with _client(srv, "lead") as client:
        assert (await client.put(
            f"{_url(ids)}/{other_id}", json={"role": "tester"}
        )).status_code == 404
        assert (await client.delete(f"{_url(ids)}/{other_id}")).status_code == 404
