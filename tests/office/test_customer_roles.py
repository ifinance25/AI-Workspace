"""У43-09: роли заказчика читают, но не пишут.

Представитель заказчика видит версии брифа своего проекта, но не кладёт новые
(403), учётка только с ролями заказчика не создаёт проекты офиса (403). Менеджер
и новый сотрудник без ролей работают как раньше.
"""
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

# Тестовый пароль локальных аккаунтов, не секрет.
_PASSWORD = "test-only-password"
_PASSPORT = {"name": "Лендинг", "work_kind": "site", "nature": "custom", "request_key": "k1"}


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
    try:
        yield srv, sm
    finally:
        srv.office_store.close()
        sm.close_sync()
        sm._engine.sync_engine.dispose()


def _user(sm: SessionManager, username: str) -> int:
    return sm.create_local_user(
        username=username, password_hash=hash_password(_PASSWORD), is_admin=False
    )


@asynccontextmanager
async def _client(srv: WebServer, username: str):
    transport = ASGITransport(app=srv.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/auth/login", json={"username": username, "password": _PASSWORD})
        assert r.status_code == 200
        yield client


async def test_customer_reads_brief_but_cannot_write(server) -> None:
    srv, sm = server
    manager, customer = _user(sm, "pm"), _user(sm, "cust")
    project = srv.office_store.create_project(name="Лендинг", created_by=manager)
    tenancy.record_creator(srv.office_store, project["id"], manager)
    srv.office_store.add_member(project["id"], customer, "customer_representative")
    pid = project["id"]
    async with _client(srv, "pm") as client:
        ok = await client.post(f"/api/office/projects/{pid}/brief", json={"text": "# Бриф"})
        assert ok.status_code == 201
    async with _client(srv, "cust") as client:
        refused = await client.post(
            f"/api/office/projects/{pid}/brief", json={"text": "# Правка заказчика"}
        )
        assert refused.status_code == 403
        listed = await client.get(f"/api/office/projects/{pid}/brief/versions")
        assert listed.status_code == 200
        assert len(listed.json()) == 1


async def test_customer_only_account_cannot_create_projects(server) -> None:
    srv, sm = server
    manager, customer = _user(sm, "pm"), _user(sm, "cust")
    _user(sm, "new")
    project = srv.office_store.create_project(name="Лендинг", created_by=manager)
    tenancy.record_creator(srv.office_store, project["id"], manager)
    srv.office_store.add_member(project["id"], customer, "customer_signatory")
    async with _client(srv, "cust") as client:
        refused = await client.post("/api/office/projects", json=_PASSPORT)
        assert refused.status_code == 403
    async with _client(srv, "new") as client:
        created = await client.post("/api/office/projects", json=_PASSPORT)
        assert created.status_code == 201
    async with _client(srv, "pm") as client:
        created = await client.post("/api/office/projects", json={**_PASSPORT, "request_key": "k2"})
        assert created.status_code == 201


def test_tenancy_rules(server) -> None:
    srv, sm = server
    store = srv.office_store
    manager, customer = _user(sm, "pm"), _user(sm, "cust")
    project = store.create_project(name="Лендинг", created_by=manager)
    tenancy.record_creator(store, project["id"], manager)
    store.add_member(project["id"], customer, "customer_representative")
    pid = project["id"]
    assert tenancy.can_write(store, pid, actor_id=manager, is_admin=False)
    assert not tenancy.can_write(store, pid, actor_id=customer, is_admin=False)
    assert tenancy.can_write(store, pid, actor_id=customer, is_admin=True)
    assert not tenancy.can_write(store, pid, actor_id=999, is_admin=False)
    assert not tenancy.can_create_project(store, actor_id=customer, is_admin=False)
    assert tenancy.can_create_project(store, actor_id=manager, is_admin=False)
    assert tenancy.can_create_project(store, actor_id=12345, is_admin=False)
    assert store.list_roles_for_user(customer) == ["customer_representative"]
