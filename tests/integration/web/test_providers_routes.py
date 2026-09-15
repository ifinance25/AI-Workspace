"""REST /api/providers: ключи Claude и Kimi, 501 без store.

Старый /api/apikey остаётся: см. test_apikey_routes.py.
GET отдаёт только метаданные, никогда сам ключ.
"""
from __future__ import annotations

import hashlib
import hmac
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from starlette.testclient import TestClient

from src.apikeys.crypto import ApiKeyCrypto
from src.apikeys.store import ApiKeyStore
from src.apikeys.validate import ProbeResult
from src.config.settings import WebSettings
from src.web import routes_providers
from src.web.server import WebServer

VALID_CLAUDE = "sk-ant-api03-SECRETMIDDLE" + "0" * 40
VALID_KIMI = "sk-kimi-EXAMPLEKEY" + "0" * 16


def _sign(bot_token: str, payload: dict) -> dict:
    secret = hashlib.sha256(bot_token.encode()).digest()
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()) if k != "hash")
    sig = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return {**payload, "hash": sig}


@pytest.fixture
def tmp_dir():
    path = Path(tempfile.mkdtemp())
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _make_store(tmp_dir: Path) -> ApiKeyStore:
    crypto = ApiKeyCrypto(Fernet.generate_key().decode())
    return ApiKeyStore(tmp_dir / "sessions.db", crypto)


def _make_server(api_key_store) -> WebServer:
    settings = WebSettings(
        enabled=True,
        host="127.0.0.1",
        port=0,
        jwt_secret="x" * 32,
        telegram_bot_username="t",
    )
    return WebServer(
        settings=settings,
        allowed_user_ids=[100],
        bot_username="t",
        session_manager=None,
        event_bus=None,
        bot_token="12345:abc",
        jwt_secret="x" * 32,
        api_key_store=api_key_store,
    )


def _login(client: TestClient, user_id: int = 100) -> None:
    login = _sign(
        "12345:abc",
        {"id": user_id, "first_name": "A", "auth_date": int(time.time())},
    )
    resp = client.post("/api/auth/telegram", json=login)
    assert resp.status_code == 200, resp.text


def _patch_probe(monkeypatch, result: ProbeResult) -> None:
    async def _fake_probe(
        key: str, timeout: float = 10.0, *, provider: str = "claude"
    ) -> ProbeResult:
        return result

    monkeypatch.setattr(routes_providers, "probe_key", _fake_probe)


def test_get_lists_four_providers_without_secrets(tmp_dir):
    store = _make_store(tmp_dir)
    store.set_key(100, VALID_CLAUDE, status="active", provider="claude")
    server = _make_server(store)
    try:
        with TestClient(server.app) as client:
            _login(client)
            resp = client.get("/api/providers")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            ids = [p["id"] for p in body["providers"]]
            assert ids == ["claude", "openai", "cursor", "kimi"]
            labels = [p["label"] for p in body["providers"]]
            assert labels == ["Claude Code", "OpenAI", "Cursor API", "Kimi Code"]
            claude = body["providers"][0]
            assert claude["status"] == "active"
            assert claude["last4"] == "0000"
            assert claude["connected"] is True
            assert "SECRETMIDDLE" not in resp.text
            assert VALID_CLAUDE not in resp.text
            assert isinstance(body["privileged"], bool)
            assert body["active_provider"] == "claude"
    finally:
        store.close()


def test_put_claude_and_kimi_saves_isolated_keys(tmp_dir, monkeypatch):
    store = _make_store(tmp_dir)
    _patch_probe(monkeypatch, ProbeResult.VALID)
    server = _make_server(store)
    try:
        with TestClient(server.app) as client:
            _login(client)

            resp = client.put("/api/providers/claude", json={"api_key": VALID_CLAUDE})
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "active"
            assert resp.json()["message"] == "API key saved"

            resp = client.put("/api/providers/kimi", json={"api_key": VALID_KIMI})
            assert resp.status_code == 200, resp.text
            assert resp.json()["status"] == "active"

            assert store.get_key(100, "claude") == VALID_CLAUDE
            assert store.get_key(100, "kimi") == VALID_KIMI
            assert "SECRETMIDDLE" not in resp.text
            assert VALID_KIMI not in resp.text

            listing = client.get("/api/providers").json()
            by_id = {p["id"]: p for p in listing["providers"]}
            assert by_id["claude"]["last4"] == "0000"
            assert by_id["kimi"]["last4"] == VALID_KIMI[-4:]
            assert by_id["claude"]["connected"] is True
            assert by_id["kimi"]["connected"] is True
    finally:
        store.close()


def test_all_verbs_501_when_store_none():
    server = _make_server(None)
    with TestClient(server.app) as client:
        _login(client)

        resp = client.get("/api/providers")
        assert resp.status_code == 501, resp.text

        resp = client.put("/api/providers/claude", json={"api_key": VALID_CLAUDE})
        assert resp.status_code == 501, resp.text

        resp = client.put("/api/providers/kimi", json={"api_key": VALID_KIMI})
        assert resp.status_code == 501, resp.text

        resp = client.delete("/api/providers/claude")
        assert resp.status_code == 501, resp.text

        resp = client.patch("/api/providers/active", json={"provider": "claude"})
        assert resp.status_code == 501, resp.text
