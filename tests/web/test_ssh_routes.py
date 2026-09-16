"""REST /api/ssh: профиль без секретов в GET, PUT шифрует ключ."""
from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from starlette.testclient import TestClient

from src.config.settings import WebSettings
from src.connections.crypto import SecretBox
from src.ssh.store import SshStore
from src.web.server import WebServer


def _sign(bot_token: str, payload: dict) -> dict:
    secret = hashlib.sha256(bot_token.encode()).digest()
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()) if k != "hash")
    sig = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return {**payload, "hash": sig}


def _pem() -> str:
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _make_store(tmp_path: Path) -> SshStore:
    return SshStore(tmp_path / "ssh.db", SecretBox(Fernet.generate_key().decode()))


def _make_server(ssh_store) -> WebServer:
    settings = WebSettings(
        enabled=True,
        host="127.0.0.1",
        port=0,
        jwt_secret="x" * 32,
        telegram_bot_username="t",
    )
    return WebServer(
        settings=settings,
        allowed_user_ids=[100, 200],
        bot_username="t",
        session_manager=None,
        event_bus=None,
        bot_token="12345:abc",
        jwt_secret="x" * 32,
        ssh_store=ssh_store,
    )


def _login(client: TestClient, user_id: int = 100) -> None:
    login = _sign(
        "12345:abc",
        {"id": user_id, "first_name": "A", "auth_date": int(time.time())},
    )
    resp = client.post("/api/auth/telegram", json=login)
    assert resp.status_code == 200, resp.text


def test_disabled_store_get_enabled_false():
    server = _make_server(None)
    with TestClient(server.app) as client:
        _login(client)
        resp = client.get("/api/ssh")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["configured"] is False
        assert "private_key" not in body


def test_put_get_never_returns_key(tmp_path):
    store = _make_store(tmp_path)
    server = _make_server(store)
    pem = _pem()
    with TestClient(server.app) as client:
        _login(client)
        empty = client.get("/api/ssh")
        assert empty.json()["configured"] is False
        put = client.put(
            "/api/ssh",
            json={
                "host": "example.com",
                "port": 22,
                "username": "ubuntu",
                "private_key": pem,
            },
        )
        assert put.status_code == 200, put.text
        body = put.json()
        assert body["configured"] is True
        assert body["has_key"] is True
        assert body["host"] == "example.com"
        assert body["username"] == "ubuntu"
        assert body["fingerprint"].startswith("SHA256:")
        assert "private_key" not in body
        assert "passphrase" not in body
        dumped = str(body)
        assert "BEGIN" not in dumped
        got = client.get("/api/ssh").json()
        assert got["fingerprint"] == body["fingerprint"]
        assert "private_key" not in got
        assert pem not in str(got)


def test_put_without_key_rejected(tmp_path):
    store = _make_store(tmp_path)
    server = _make_server(store)
    with TestClient(server.app) as client:
        _login(client)
        resp = client.put(
            "/api/ssh",
            json={"host": "example.com", "port": 22, "username": "ubuntu"},
        )
        assert resp.status_code == 422


def test_put_garbage_key_rejected(tmp_path):
    store = _make_store(tmp_path)
    server = _make_server(store)
    with TestClient(server.app) as client:
        _login(client)
        resp = client.put(
            "/api/ssh",
            json={
                "host": "example.com",
                "port": 22,
                "username": "ubuntu",
                "private_key": "not-a-key",
            },
        )
        assert resp.status_code == 422


def test_update_host_keeps_existing_key(tmp_path):
    store = _make_store(tmp_path)
    server = _make_server(store)
    pem = _pem()
    with TestClient(server.app) as client:
        _login(client)
        first = client.put(
            "/api/ssh",
            json={
                "host": "old.example",
                "port": 22,
                "username": "ubuntu",
                "private_key": pem,
            },
        )
        fp = first.json()["fingerprint"]
        second = client.put(
            "/api/ssh",
            json={"host": "new.example", "port": 2222, "username": "deploy"},
        )
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["host"] == "new.example"
        assert body["port"] == 2222
        assert body["username"] == "deploy"
        assert body["fingerprint"] == fp
        saved = store.get(100)
        assert saved is not None
        assert saved.private_key == pem.strip()


def test_profiles_are_per_user(tmp_path):
    store = _make_store(tmp_path)
    server = _make_server(store)
    pem = _pem()
    with TestClient(server.app) as client:
        _login(client, 100)
        client.put(
            "/api/ssh",
            json={
                "host": "one.example",
                "port": 22,
                "username": "a",
                "private_key": pem,
            },
        )
        _login(client, 200)
        other = client.get("/api/ssh").json()
        assert other["configured"] is False


def test_delete_profile(tmp_path):
    store = _make_store(tmp_path)
    server = _make_server(store)
    pem = _pem()
    with TestClient(server.app) as client:
        _login(client)
        client.put(
            "/api/ssh",
            json={
                "host": "example.com",
                "port": 22,
                "username": "ubuntu",
                "private_key": pem,
            },
        )
        deleted = client.delete("/api/ssh")
        assert deleted.status_code == 200
        assert client.get("/api/ssh").json()["configured"] is False
        again = client.delete("/api/ssh")
        assert again.status_code == 404


def test_unauthenticated_rejected():
    server = _make_server(None)
    with TestClient(server.app) as client:
        assert client.get("/api/ssh").status_code == 401
