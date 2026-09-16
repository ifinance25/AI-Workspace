"""WS /api/ws/ssh: без профиля закрывается, с фейковым SSH гоняет ввод/вывод."""
from __future__ import annotations

import asyncio
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
from src.ssh.keys import fingerprint_private_key
from src.ssh.store import SshProfile, SshStore
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


class _FakeStdin:
    def __init__(self):
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)


class _FakeStdout:
    def __init__(self, first: bytes):
        self._first = first
        self._sent = False
        self._hang = asyncio.Event()

    async def read(self, _n: int) -> bytes:
        if not self._sent:
            self._sent = True
            return self._first
        await self._hang.wait()
        return b""


class _FakeProcess:
    def __init__(self):
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(b"welcome\n")
        self.size = None

    def change_terminal_size(self, cols, rows) -> None:
        self.size = (cols, rows)

    def close(self) -> None:
        self.stdout._hang.set()

    async def wait_closed(self) -> None:
        return None


class _FakeConn:
    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


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
        allowed_user_ids=[100],
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


def test_ws_without_profile_closes(tmp_path):
    store = _make_store(tmp_path)
    server = _make_server(store)
    with TestClient(server.app) as client:
        _login(client)
        try:
            with client.websocket_connect("/api/ws/ssh"):
                raise AssertionError("handshake should fail")
        except Exception:
            pass


def test_ws_echo_with_fake_shell(tmp_path, monkeypatch):
    store = _make_store(tmp_path)
    pem = _pem()
    store.save(
        100,
        SshProfile(
            host="example.com",
            port=22,
            username="ubuntu",
            private_key=pem,
            passphrase=None,
            fingerprint=fingerprint_private_key(pem),
        ),
    )
    fake_proc = _FakeProcess()
    fake_conn = _FakeConn()

    async def _open(profile, *, cols=80, rows=24):
        assert profile.host == "example.com"
        fake_proc.change_terminal_size(cols, rows)
        return fake_conn, fake_proc

    monkeypatch.setattr("src.ssh.session.open_ssh_shell", _open)
    server = _make_server(store)
    with TestClient(server.app) as client:
        _login(client)
        with client.websocket_connect("/api/ws/ssh") as ws:
            ready = ws.receive_json()
            assert ready["type"] == "ready"
            assert ready["host"] == "example.com"
            out = ws.receive_json()
            assert out["type"] == "out"
            assert "welcome" in out["data"]
            ws.send_json({"type": "in", "data": "ls\n"})
            ws.send_json({"type": "resize", "cols": 120, "rows": 40})
            deadline = time.time() + 2
            while time.time() < deadline and (
                not fake_proc.stdin.written or fake_proc.size != (120, 40)
            ):
                time.sleep(0.05)
            assert fake_proc.stdin.written[0] == b"ls\n"
            assert fake_proc.size == (120, 40)
