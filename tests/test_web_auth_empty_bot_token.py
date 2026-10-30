"""У43-03: вход через Telegram без токена бота закрыт.

Подпись виджета считается от sha256(bot_token). При пустом токене это sha256(""),
и любой, кто знает id из белого списка, собирает валидную подпись сам. Путь
должен отвечать 404 до проверки подписи, а сама проверка отказывать пустому токену.
"""
from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from httpx import ASGITransport, AsyncClient

from src.config.settings import WebSettings
from src.web.auth import verify_telegram_login
from src.web.server import WebServer


def _forge(payload: dict) -> dict:
    """Подпись от пустого токена: ровно то, что мог бы собрать посторонний."""
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    sig = hmac.new(hashlib.sha256(b"").digest(), data_check.encode(), hashlib.sha256).hexdigest()
    return {**payload, "hash": sig}


def test_verify_rejects_empty_bot_token() -> None:
    payload = _forge({"id": 777, "first_name": "x", "auth_date": int(time.time())})
    with pytest.raises(ValueError, match="bot token"):
        verify_telegram_login(payload, bot_token="", allowed_user_ids=[777])


async def test_route_is_closed_without_bot_token() -> None:
    settings = WebSettings(
        enabled=True, host="127.0.0.1", port=0, jwt_secret="x" * 32, telegram_bot_username=""
    )
    server = WebServer(
        settings=settings,
        allowed_user_ids=[777],
        bot_username="",
        session_manager=None,
        event_bus=None,
        bot_token="",
        jwt_secret="x" * 32,
    )
    payload = _forge({"id": 777, "first_name": "x", "auth_date": int(time.time())})
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/auth/telegram", json=payload)
    assert resp.status_code == 404
    assert "ai_workspace_session" not in resp.cookies
