"""GET /api/me: булев флаг kb_search_enabled без адреса и ключа общей базы знаний."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.claude import SessionManager
from src.config.settings import Settings
from src.connections.resolver import build_shared_mcp_servers
from src.event_bus import EventBus
from src.web.passwords import hash_password
from src.web.server import WebServer

pytestmark = pytest.mark.asyncio

FAKE_URL = "https://kb.example.invalid/mcp-secret-path"
FAKE_KEY = "fake-kb-key-0123456789"


@pytest.fixture
def make_server():
    """WebServer получает настоящие настройки, как в scripts/run_web.py."""
    tmp = Path(tempfile.mkdtemp())
    sm = SessionManager(storage_path=tmp / "sessions.db")
    sm.create_local_user(username="u", password_hash=hash_password("pw123456"), is_admin=False)

    def _make(settings: Settings) -> WebServer:
        web = settings.web.model_copy(
            update={"enabled": True, "host": "127.0.0.1", "port": 0, "jwt_secret": "x" * 32}
        )
        return WebServer(
            settings=web,
            allowed_user_ids=[100], bot_username="b", session_manager=sm,
            event_bus=EventBus(), bot_token="12345:abc", jwt_secret="x" * 32,
            project_paths=[tmp], kb_search_enabled=bool(build_shared_mcp_servers(settings)),
        )

    try:
        yield _make
    finally:
        sm.close_sync()
        sm._engine.sync_engine.dispose()
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def real_settings(monkeypatch):
    def _settings(url: str, key: str, *, transport: str = "sdk") -> Settings:
        monkeypatch.setenv("KB_MCP_URL", url)
        monkeypatch.setenv("KB_MCP_KEY", key)
        settings = Settings(_env_file=None)
        settings.claude.transport = transport
        return settings

    return _settings


async def _me(server: WebServer):
    async with AsyncClient(transport=ASGITransport(app=server.app), base_url="http://test") as c:
        await c.post("/api/auth/login", json={"username": "u", "password": "pw123456"})
        return await c.get("/api/me")


async def test_flag_true_without_secrets(make_server, real_settings):
    r = await _me(make_server(real_settings(FAKE_URL, FAKE_KEY)))
    assert r.status_code == 200
    assert r.json()["kb_search_enabled"] is True
    assert FAKE_URL not in r.text and FAKE_KEY not in r.text
    assert "kb.example" not in r.text


@pytest.mark.parametrize("url,key", [("", FAKE_KEY), (FAKE_URL, ""), ("", "")])
async def test_flag_false_when_url_or_key_empty(make_server, real_settings, url, key):
    r = await _me(make_server(real_settings(url, key)))
    assert r.json()["kb_search_enabled"] is False
    assert FAKE_KEY not in r.text


@pytest.mark.parametrize("transport", ["tmux", "cli"])
async def test_flag_false_on_other_transport(make_server, real_settings, transport):
    r = await _me(make_server(real_settings(FAKE_URL, FAKE_KEY, transport=transport)))
    assert r.json()["kb_search_enabled"] is False


async def test_flag_false_when_record_cannot_be_built(make_server, real_settings, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("сборка не удалась")

    monkeypatch.setattr("src.connections.kb_tools.build_kb_server", _boom)
    r = await _me(make_server(real_settings(FAKE_URL, FAKE_KEY)))
    assert r.json()["kb_search_enabled"] is False


async def test_flag_false_on_plain_http(make_server, real_settings):
    r = await _me(make_server(real_settings("http://kb.example.invalid/mcp", FAKE_KEY)))
    assert r.json()["kb_search_enabled"] is False
