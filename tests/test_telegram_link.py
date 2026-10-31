"""Привязка Telegram к локальной учётке: код, подтверждение паролем, отзыв."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.office.storage import OfficeStore, hash_channel_code
from src.web.passwords import hash_password
from src.web.routes_members import _resolve_identifier
from src.web.server import WebServer

PASSWORD = "correct-horse-battery"
ADMIN_PASSWORD = "admin-horse-battery"
TEAM_TG = "7900000000"


@pytest.fixture
def env(tmp_path: Path):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    server = WebServer(
        settings=WebSettings(
            enabled=True, host="127.0.0.1", port=0, jwt_secret="x" * 32,
            telegram_bot_username="paneltestbot",
        ),
        allowed_user_ids=[100],
        bot_username="paneltestbot",
        session_manager=sm,
        event_bus=EventBus(),
        bot_token="12345:abc",
    )
    server.telegram_bot_enabled = True
    uid = sm.create_local_user(
        username="ivan", password_hash=hash_password(PASSWORD), is_admin=False
    )
    admin_id = sm.create_local_user(
        username="boss", password_hash=hash_password(ADMIN_PASSWORD), is_admin=True
    )
    with TestClient(server.app) as client, TestClient(server.app) as admin:
        assert client.post(
            "/api/auth/login", json={"username": "ivan", "password": PASSWORD}
        ).status_code == 200
        assert admin.post(
            "/api/auth/login", json={"username": "boss", "password": ADMIN_PASSWORD}
        ).status_code == 200
        yield SimpleNamespace(
            sm=sm, server=server, store=server.office_store,
            client=client, admin=admin, uid=uid, admin_id=admin_id,
        )
    sm.close_sync()
    sm._engine.sync_engine.dispose()


def _start(env, client=None) -> str:
    resp = (client or env.client).post("/api/me/telegram/start")
    assert resp.status_code == 200
    link = resp.json()["deep_link"]
    assert link.startswith("https://t.me/paneltestbot?start=bind_")
    return link.rsplit("bind_", 1)[1]


def _telegram_presses_start(env, code: str, telegram_id: str = TEAM_TG) -> bool:
    return env.store.mark_channel_binding_started(
        hash_channel_code(code), "telegram", telegram_id, "ivan",
        confirm_expires_at=time.time() + 60,
    )


def _bind(env, client=None, telegram_id: str = TEAM_TG):
    code = _start(env, client)
    assert _telegram_presses_start(env, code, telegram_id)
    return (client or env.client).post(
        "/api/me/telegram/confirm",
        json={"password": PASSWORD, "external_user_id": telegram_id},
    )


# --- Хранилище ------------------------------------------------------------


def test_code_is_stored_as_hash_only(env, tmp_path):
    code = _start(env)
    with sqlite3.connect(tmp_path / "sessions.db") as raw:
        dump = "\n".join(raw.iterdump())
    assert code not in dump
    assert hash_channel_code(code) in dump


def test_expired_code_is_refused(tmp_path):
    store = OfficeStore(tmp_path / "o.db")
    store.start_channel_binding(1, "telegram", "h", code_expires_at=100.0)
    assert not store.mark_channel_binding_started(
        "h", "telegram", TEAM_TG, "ivan", confirm_expires_at=900.0, now=101.0
    )
    store.close()


def test_code_works_once(tmp_path):
    store = OfficeStore(tmp_path / "o.db")
    store.start_channel_binding(1, "telegram", "h", code_expires_at=100.0)
    assert store.mark_channel_binding_started(
        "h", "telegram", TEAM_TG, "ivan", confirm_expires_at=900.0, now=50.0
    )
    assert not store.mark_channel_binding_started(
        "h", "telegram", "666", "evil", confirm_expires_at=900.0, now=51.0
    )
    assert store.get_channel_binding(1, "telegram")["external_user_id"] == TEAM_TG
    store.close()


def test_new_start_cancels_old_code(tmp_path):
    store = OfficeStore(tmp_path / "o.db")
    store.start_channel_binding(1, "telegram", "old", code_expires_at=100.0)
    store.start_channel_binding(1, "telegram", "new", code_expires_at=100.0)
    assert not store.mark_channel_binding_started(
        "old", "telegram", TEAM_TG, "ivan", confirm_expires_at=900.0, now=50.0
    )
    store.close()


def test_confirm_window_expires(tmp_path):
    store = OfficeStore(tmp_path / "o.db")
    store.start_channel_binding(1, "telegram", "h", code_expires_at=100.0)
    store.mark_channel_binding_started(
        "h", "telegram", TEAM_TG, "ivan", confirm_expires_at=200.0, now=50.0
    )
    assert store.confirm_channel_binding(1, "telegram", TEAM_TG, now=201.0) is None
    store.close()


def test_duplicate_active_binding_rejected_by_database(tmp_path):
    from src.office.storage import ChannelBindingConflictError

    store = OfficeStore(tmp_path / "o.db")
    for user_id, code_hash in ((1, "a"), (2, "b")):
        store.start_channel_binding(user_id, "telegram", code_hash, code_expires_at=100.0)
        store.mark_channel_binding_started(
            code_hash, "telegram", TEAM_TG, "ivan", confirm_expires_at=200.0, now=50.0
        )
    store.confirm_channel_binding(1, "telegram", TEAM_TG, now=60.0)
    with pytest.raises(ChannelBindingConflictError):
        store.confirm_channel_binding(2, "telegram", TEAM_TG, now=60.0)
    store.close()


# --- API ------------------------------------------------------------------


def test_routes_require_login(env):
    env.client.cookies.clear()
    assert env.client.get("/api/me/telegram").status_code == 401
    assert env.client.post("/api/me/telegram/start").status_code == 401


def test_status_shows_account_before_confirm(env):
    assert env.client.get("/api/me/telegram").json()["state"] == "none"
    code = _start(env)
    assert env.client.get("/api/me/telegram").json()["state"] == "waiting_start"
    _telegram_presses_start(env, code)
    data = env.client.get("/api/me/telegram").json()
    assert data["state"] == "waiting_confirm"
    assert data["username"] == "ivan"
    assert data["external_user_id"] == TEAM_TG


def test_start_needs_running_bot(env):
    env.server.telegram_bot_enabled = False
    assert env.client.post("/api/me/telegram/start").status_code == 404
    assert env.client.get("/api/me/telegram").json()["available"] is False


def test_whitelist_account_cannot_bind(env):
    from src.web.auth import issue_jwt

    env.sm.record_telegram_user(100, "owner")
    env.client.cookies.set(
        "ai_workspace_session",
        issue_jwt({"user_id": 100, "username": "owner", "is_admin": False},
                  secret="x" * 32, ttl_seconds=60),
    )
    assert env.client.post("/api/me/telegram/start").status_code == 403


def test_confirm_with_right_password(env):
    resp = _bind(env)
    assert resp.status_code == 200
    assert env.client.get("/api/me/telegram").json()["state"] == "active"
    assert env.store.find_active_binding("telegram", TEAM_TG)["user_id"] == env.uid


def test_confirm_with_wrong_password(env):
    code = _start(env)
    _telegram_presses_start(env, code)
    resp = env.client.post(
        "/api/me/telegram/confirm", json={"password": "wrong", "external_user_id": TEAM_TG}
    )
    assert resp.status_code == 401
    assert env.store.find_active_binding("telegram", TEAM_TG) is None


def test_confirm_refuses_swapped_account(env):
    """Вор сессии подменил аккаунт, пока владелец вводит пароль за показанный."""
    _telegram_presses_start(env, _start(env), TEAM_TG)
    shown = env.client.get("/api/me/telegram").json()["external_user_id"]
    _telegram_presses_start(env, _start(env), "666")
    resp = env.client.post(
        "/api/me/telegram/confirm", json={"password": PASSWORD, "external_user_id": shown}
    )
    assert resp.status_code == 409
    assert env.store.find_active_binding("telegram", "666") is None
    assert env.client.get("/api/me/telegram").json()["state"] == "waiting_confirm"


def test_confirm_is_rate_limited(env):
    code = _start(env)
    _telegram_presses_start(env, code)
    statuses = [
        env.client.post(
            "/api/me/telegram/confirm", json={"password": "wrong", "external_user_id": TEAM_TG}
        ).status_code
        for _ in range(12)
    ]
    assert 429 in statuses
    resp = env.client.post(
        "/api/me/telegram/confirm", json={"password": PASSWORD, "external_user_id": TEAM_TG}
    )
    assert resp.status_code == 429


def test_confirm_without_start_is_409(env):
    resp = env.client.post(
        "/api/me/telegram/confirm", json={"password": PASSWORD, "external_user_id": TEAM_TG}
    )
    assert resp.status_code == 409


def test_one_telegram_one_account(env):
    assert _bind(env).status_code == 200
    env.sm.create_local_user(
        username="petr", password_hash=hash_password(PASSWORD), is_admin=False
    )
    with TestClient(env.server.app) as other:
        assert other.post(
            "/api/auth/login", json={"username": "petr", "password": PASSWORD}
        ).status_code == 200
        assert _bind(env, other).status_code == 409


def test_second_binding_needs_unbind(env):
    assert _bind(env).status_code == 200
    assert env.client.post("/api/me/telegram/start").status_code == 409


def test_self_unbind_closes_all_sessions(env):
    assert _bind(env).status_code == 200
    assert env.client.delete("/api/me/telegram").status_code == 200
    assert env.store.find_active_binding("telegram", TEAM_TG) is None
    assert env.client.get("/api/me").status_code == 401


def test_cancelling_pending_attempt_keeps_session(env):
    _telegram_presses_start(env, _start(env))
    assert env.client.delete("/api/me/telegram").status_code == 200
    assert env.client.get("/api/me/telegram").json()["state"] == "none"
    assert env.client.get("/api/me").status_code == 200


# --- Админ ----------------------------------------------------------------


def test_admin_unbind_closes_sessions(env):
    assert _bind(env).status_code == 200
    assert env.admin.delete(f"/api/admin/users/{env.uid}/telegram").status_code == 200
    assert env.store.find_active_binding("telegram", TEAM_TG) is None
    assert env.client.get("/api/me").status_code == 401


def test_only_admin_can_unbind_others(env):
    assert _bind(env).status_code == 200
    assert env.client.delete(f"/api/admin/users/{env.admin_id}/telegram").status_code == 403


def test_password_reset_removes_binding(env):
    assert _bind(env).status_code == 200
    resp = env.admin.post(
        f"/api/admin/users/{env.uid}/password", json={"password": "new-password-123"}
    )
    assert resp.status_code == 200
    assert env.store.find_active_binding("telegram", TEAM_TG) is None


def test_deleting_user_frees_telegram(env):
    assert _bind(env).status_code == 200
    assert env.admin.delete(f"/api/admin/users/{env.uid}").status_code == 200
    assert env.store.find_active_binding("telegram", TEAM_TG) is None


def test_promotion_to_admin_closes_telegram_session(env):
    assert _bind(env).status_code == 200
    resp = env.admin.post(f"/api/admin/users/{env.uid}/admin", json={"is_admin": True})
    assert resp.status_code == 200
    assert env.client.get("/api/me").status_code == 401


def test_admin_list_shows_name_without_telegram_id(env):
    assert _bind(env).status_code == 200
    rows = env.admin.get("/api/admin/users").json()
    row = next(r for r in rows if r["user_id"] == env.uid)
    assert row["telegram_username"] == "ivan"
    assert TEAM_TG not in str(rows)


def test_member_invite_finds_account_by_telegram_id(env):
    assert _bind(env).status_code == 200
    assert _resolve_identifier(env.sm, TEAM_TG, env.store) == env.uid
    assert _resolve_identifier(env.sm, "ivan", env.store) == env.uid
