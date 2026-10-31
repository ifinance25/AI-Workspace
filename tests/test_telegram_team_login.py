"""Вход участника команды через Telegram: своя учётка, никаких прав белого списка."""
from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from types import SimpleNamespace

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from src.bot.permissions import is_bot_privileged
from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.web.passwords import hash_password
from src.web.project_access import resolve_project_access
from src.web.routes_ws import no_project_readonly
from src.web.server import WebServer

BOT_TOKEN = "12345:abc"
JWT_SECRET = "x" * 32
OWNER_ID = 100
TEAM_TG = 7_900_000_000
STRANGER_TG = 7_900_000_001


def _sign(fields: dict) -> dict:
    data = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hashlib.sha256(BOT_TOKEN.encode()).digest()
    return {**fields, "hash": hmac.new(secret, data.encode(), hashlib.sha256).hexdigest()}


def _widget(telegram_id: int, **extra) -> dict:
    return _sign({"id": telegram_id, "first_name": "A", "auth_date": int(time.time()), **extra})


def _bind(store, user_id: int, telegram_id: int = TEAM_TG) -> None:
    store.start_channel_binding(user_id, "telegram", "hash", code_expires_at=time.time() + 60)
    assert store.mark_channel_binding_started(
        "hash", "telegram", str(telegram_id), "ivan", confirm_expires_at=time.time() + 60
    )
    assert store.confirm_channel_binding(user_id, "telegram") is not None


@pytest.fixture
def env(tmp_path: Path):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    server = WebServer(
        settings=WebSettings(
            enabled=True, host="127.0.0.1", port=0, jwt_secret=JWT_SECRET,
            telegram_bot_username="paneltestbot",
        ),
        allowed_user_ids=[OWNER_ID],
        bot_username="paneltestbot",
        session_manager=sm,
        event_bus=EventBus(),
        bot_token=BOT_TOKEN,
    )
    uid = sm.create_local_user(
        username="ivan", password_hash=hash_password("x" * 12), is_admin=False
    )
    with TestClient(server.app) as client:
        yield SimpleNamespace(
            sm=sm, server=server, store=server.office_store, client=client, uid=uid
        )
    sm.close_sync()
    sm._engine.sync_engine.dispose()


def test_widget_opens_local_account(env):
    _bind(env.store, env.uid)
    resp = env.client.post("/api/auth/telegram", json=_widget(TEAM_TG))
    assert resp.status_code == 200
    assert resp.json()["user"] == {"id": env.uid, "username": "ivan", "is_admin": False}
    me = env.client.get("/api/me").json()
    assert me["id"] == env.uid
    assert me["is_admin"] is False
    assert me["can_continue_in_telegram"] is False
    claims = pyjwt.decode(
        env.client.cookies["ai_workspace_session"], JWT_SECRET, algorithms=["HS256"]
    )
    assert claims["user_id"] == env.uid
    assert claims["tv"] == 0


def test_stranger_gets_403_and_leaves_no_user_row(env):
    resp = env.client.post("/api/auth/telegram", json=_widget(STRANGER_TG))
    assert resp.status_code == 403
    assert env.sm.get_user_by_id(STRANGER_TG) is None


def test_team_login_leaves_no_telegram_user_row(env):
    _bind(env.store, env.uid)
    assert env.client.post("/api/auth/telegram", json=_widget(TEAM_TG)).status_code == 200
    assert env.sm.get_user_by_id(TEAM_TG) is None


def test_bad_signature_is_401(env):
    _bind(env.store, env.uid)
    forged = {**_widget(TEAM_TG), "hash": "0" * 64}
    assert env.client.post("/api/auth/telegram", json=forged).status_code == 401


def test_replay_is_401(env):
    _bind(env.store, env.uid)
    payload = _widget(TEAM_TG)
    assert env.client.post("/api/auth/telegram", json=payload).status_code == 200
    assert env.client.post("/api/auth/telegram", json=payload).status_code == 401


def test_admin_account_cannot_enter_through_telegram(env):
    _bind(env.store, env.uid)
    env.sm.set_user_admin(env.uid, True)
    assert env.client.post("/api/auth/telegram", json=_widget(TEAM_TG)).status_code == 403


def test_disabled_account_cannot_enter_through_telegram(env):
    _bind(env.store, env.uid)
    env.sm.set_user_active(env.uid, False)
    assert env.client.post("/api/auth/telegram", json=_widget(TEAM_TG)).status_code == 403


def test_revoked_binding_closes_login(env):
    _bind(env.store, env.uid)
    env.store.revoke_channel_binding(env.uid, "telegram")
    assert env.client.post("/api/auth/telegram", json=_widget(TEAM_TG)).status_code == 403


def test_pending_binding_does_not_open_login(env):
    env.store.start_channel_binding(env.uid, "telegram", "hash", code_expires_at=time.time() + 60)
    env.store.mark_channel_binding_started(
        "hash", "telegram", str(TEAM_TG), "ivan", confirm_expires_at=time.time() + 60
    )
    assert env.client.post("/api/auth/telegram", json=_widget(TEAM_TG)).status_code == 403


def test_local_id_inside_whitelist_is_refused(env):
    """Старый локальный id совпал с id из белого списка: такой вход дал бы всё."""
    _bind(env.store, env.uid)
    env.server.allowed_user_ids.append(env.uid)
    assert env.client.post("/api/auth/telegram", json=_widget(TEAM_TG)).status_code == 403


def test_whitelist_login_unchanged(env):
    resp = env.client.post("/api/auth/telegram", json=_widget(OWNER_ID))
    assert resp.status_code == 200
    assert resp.json()["user"]["id"] == OWNER_ID


def test_magic_link_opens_local_account(env):
    _bind(env.store, env.uid)
    token = env.server.magic_link_store.create(TEAM_TG)
    resp = env.client.post("/api/auth/magic-link", json={"token": token})
    assert resp.status_code == 200
    assert resp.json()["user"]["id"] == env.uid
    assert env.client.get("/api/me").json()["id"] == env.uid
    assert env.sm.get_user_by_id(TEAM_TG) is None


def test_magic_link_for_stranger_is_403(env):
    token = env.server.magic_link_store.create(STRANGER_TG)
    assert env.client.post("/api/auth/magic-link", json={"token": token}).status_code == 403


@pytest.mark.asyncio
async def test_team_account_stays_unprivileged(env, tmp_path):
    """Страж: вход через Telegram не поднимает прав учётки."""
    _bind(env.store, env.uid)
    project = tmp_path / "secret-project"
    project.mkdir()
    access = resolve_project_access(
        str(project),
        user={"user_id": env.uid, "is_admin": False},
        project_paths=[project],
        whitelist=[OWNER_ID],
        session_manager=env.sm,
    )
    assert access.allowed is False
    assert await is_bot_privileged(env.sm, env.uid, [OWNER_ID]) is False
    assert no_project_readonly(user_id=env.uid, whitelist=[OWNER_ID], db_is_admin=False) is True


def test_auth_config_is_public(env):
    data = env.client.get("/api/auth/config").json()
    assert data == {"telegram_enabled": True, "telegram_bot_username": "paneltestbot"}


def test_new_local_ids_leave_telegram_range(env):
    uid = env.sm.create_local_user(
        username="petr", password_hash=hash_password("y" * 12), is_admin=False
    )
    assert uid > 1 << 52
    assert uid < 1 << 53  # браузер хранит число без потерь
