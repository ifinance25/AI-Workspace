"""У43-07: токен Redmine шифруется ключом CONNECTIONS_SECRET_KEY, а не подписью cookie.

Без ключа шифрования админка принимает адрес и проект, но не токен (503).
С ключом токен сохраняется и наружу уходит только последние четыре знака.
После смены ключа шифрования токен считается отсутствующим: админ вводит его заново.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.web.passwords import hash_password
from src.web.server import WebServer

# Тестовый пароль локальных аккаунтов, не секрет.
_PASSWORD = "test-only-password"


def _server(tmp_path, connections_secret_key: str = "") -> tuple[WebServer, SessionManager]:
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    settings = WebSettings(
        enabled=True, host="127.0.0.1", port=0, jwt_secret="x" * 32, telegram_bot_username="t"
    )
    srv = WebServer(
        settings=settings,
        allowed_user_ids=[],
        bot_username="t",
        session_manager=sm,
        event_bus=EventBus(),
        jwt_secret="x" * 32,
        connections_secret_key=connections_secret_key,
    )
    if sm.get_user_by_username("root") is None:
        sm.create_local_user(
            username="root", password_hash=hash_password(_PASSWORD), is_admin=True
        )
    return srv, sm


def _close(srv: WebServer, sm: SessionManager) -> None:
    srv.office_store.close()
    sm.close_sync()
    sm._engine.sync_engine.dispose()


@asynccontextmanager
async def _admin(srv: WebServer):
    async with AsyncClient(transport=ASGITransport(app=srv.app), base_url="http://test") as client:
        r = await client.post("/api/auth/login", json={"username": "root", "password": _PASSWORD})
        assert r.status_code == 200
        yield client


async def test_without_encryption_key_token_is_refused(tmp_path) -> None:
    srv, sm = _server(tmp_path)
    try:
        async with _admin(srv) as client:
            refused = await client.put(
                "/api/admin/redmine",
                json={
                    "base_url": "https://redmine.example",
                    "redmine_project": "hr",
                    "api_key": "k-1234",
                },
            )
            assert refused.status_code == 503
            assert "CONNECTIONS_SECRET_KEY" in refused.json()["detail"]
            saved = await client.put(
                "/api/admin/redmine",
                json={"base_url": "https://redmine.example", "redmine_project": "hr"},
            )
            assert saved.status_code == 200
            assert saved.json() == {
                "base_url": "https://redmine.example",
                "redmine_project": "hr",
                "has_token": False,
                "last4": "",
            }
    finally:
        _close(srv, sm)


async def test_token_is_stored_under_connections_key_and_lost_on_rotation(tmp_path) -> None:
    key = Fernet.generate_key().decode()
    srv, sm = _server(tmp_path, key)
    try:
        async with _admin(srv) as client:
            saved = await client.put(
                "/api/admin/redmine",
                json={
                    "base_url": "https://redmine.example",
                    "redmine_project": "hr",
                    "api_key": "secret-token-1234",
                },
            )
            assert saved.status_code == 200
            assert saved.json()["has_token"] is True
            assert saved.json()["last4"] == "1234"
            assert "secret-token" not in saved.text
            shown = await client.get("/api/admin/redmine")
            assert shown.json()["has_token"] is True
    finally:
        _close(srv, sm)

    # Другой ключ шифрования на том же файле базы: токен не читается, нужен ввод заново.
    rotated, sm2 = _server(tmp_path, Fernet.generate_key().decode())
    try:
        async with _admin(rotated) as client:
            shown = await client.get("/api/admin/redmine")
            assert shown.status_code == 200
            assert shown.json()["has_token"] is False
            assert shown.json()["base_url"] == "https://redmine.example"
    finally:
        _close(rotated, sm2)


async def test_plain_http_address_is_422(tmp_path) -> None:
    srv, sm = _server(tmp_path, Fernet.generate_key().decode())
    try:
        async with _admin(srv) as client:
            bad = await client.put(
                "/api/admin/redmine",
                json={
                    "base_url": "http://redmine.example",
                    "redmine_project": "hr",
                    "api_key": "k-1234",
                },
            )
            assert bad.status_code == 422
    finally:
        _close(srv, sm)
