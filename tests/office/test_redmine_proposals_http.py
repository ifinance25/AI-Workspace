"""Кнопка «Создать» под карточкой чата: задача появляется только при верной подписи."""
from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.office import redmine_mirror, tenancy
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
        connections_secret_key=Fernet.generate_key().decode(),
    )
    try:
        yield srv, sm
    finally:
        srv.office_store.close()
        sm.close_sync()
        sm._engine.sync_engine.dispose()


@asynccontextmanager
async def _client(srv: WebServer, username: str):
    async with AsyncClient(transport=ASGITransport(app=srv.app), base_url="http://test") as client:
        r = await client.post("/api/auth/login", json={"username": username, "password": _PASSWORD})
        assert r.status_code == 200
        yield client


async def test_confirm_needs_valid_signature_and_is_idempotent(server) -> None:
    srv, sm = server
    uid = sm.create_local_user(
        username="lead", password_hash=hash_password(_PASSWORD), is_admin=False
    )
    project = srv.office_store.create_project(name="Факт", created_by=uid)
    tenancy.record_creator(srv.office_store, project["id"], uid)
    redmine_mirror.seed_demo_mirror(srv.office_store, project["id"])
    pid = project["id"]
    signature = redmine_mirror.sign_proposal(_SECRET, pid, uid, "Новая тема", "Текст", "2026-12-01")
    body = {
        "subject": "Новая тема", "description": "Текст", "due_date": "2026-12-01",
        "signature": signature, "redmine_project": "demo-local",
    }
    async with _client(srv, "lead") as client:
        forged = await client.post(
            f"/api/office/projects/{pid}/redmine/proposals", json={**body, "subject": "Другая"}
        )
        assert forged.status_code == 403
        first = await client.post(f"/api/office/projects/{pid}/redmine/proposals", json=body)
        assert first.status_code == 200, first.text
        number = first.json()["issue"]["id"]
        # Повтор правит ту же задачу в Redmine; у демо-копии Redmine нет, поэтому статус
        # повтора не важен: важно, что вторая задача не появилась.
        await client.post(f"/api/office/projects/{pid}/redmine/proposals", json=body)
        listed = await client.get(f"/api/office/projects/{pid}/redmine")
        subjects = [i["subject"] for i in listed.json()["issues"] if i["subject"] == "Новая тема"]
        assert subjects == ["Новая тема"]  # двойное нажатие не создало вторую задачу
        assert number


async def test_signature_of_other_user_is_refused(server) -> None:
    srv, sm = server
    pw = hash_password(_PASSWORD)
    lead = sm.create_local_user(username="lead", password_hash=pw, is_admin=False)
    other = sm.create_local_user(username="other", password_hash=pw, is_admin=False)
    project = srv.office_store.create_project(name="Факт", created_by=lead)
    tenancy.record_creator(srv.office_store, project["id"], lead)
    srv.office_store.add_member(project["id"], other, "developer")
    redmine_mirror.seed_demo_mirror(srv.office_store, project["id"])
    pid = project["id"]
    signature = redmine_mirror.sign_proposal(_SECRET, pid, lead, "Тема", "", "")
    async with _client(srv, "other") as client:
        r = await client.post(
            f"/api/office/projects/{pid}/redmine/proposals",
            json={"subject": "Тема", "signature": signature, "redmine_project": "demo-local"},
        )
        assert r.status_code == 403
