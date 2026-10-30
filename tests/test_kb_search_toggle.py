"""Переключатель «Поиск по Базе знаний»: kb_search управляет подключением общего
сервера к запуску, личные подключения от него не зависят."""

from __future__ import annotations

import pytest

from src.claude.bridge import ClaudeEventType
from src.connections.resolver import dispatch_mcp_servers
from src.event_bus import EventBus
from src.event_bus.claude import ClaudeEventRelay
from src.event_bus.events import UserMessageReceived

FAKE_KEY = "fake-kb-key-0123456789"


class _Settings:
    def get_kb_mcp_url(self) -> str:
        return "https://kb.example.invalid/mcp"

    def get_kb_mcp_key(self) -> str:
        return FAKE_KEY

    require_user_key = False


class _Connections:
    """Хранилище с одним личным подключением (notion)."""

    def list_service_ids(self, user_id: int) -> list[str]:
        return ["notion"]

    def get_secret(self, user_id: int, service_id: str) -> str:
        return "fake-notion-token"


class _Bridge:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_message(self, **kwargs):
        from src.claude.bridge import ClaudeEvent

        self.calls.append(kwargs)
        yield ClaudeEvent(ClaudeEventType.COMPLETE, metadata={"session_id": "s", "usage": {}})


def test_event_default_is_off():
    event = UserMessageReceived(
        request_id="r", chat_id=1, topic_id=1, project_path="/tmp", text="hi"
    )
    assert event.kb_search is False


def test_dispatch_without_shared_has_no_kb_but_keeps_personal():
    servers = dispatch_mcp_servers(1, _Connections(), _Settings(), include_shared=False)
    assert servers is not None
    assert "fakt_kb" not in servers
    assert "notion" in servers


def test_dispatch_with_shared_has_only_kb():
    servers = dispatch_mcp_servers(1, _Connections(), _Settings(), include_shared=True)
    assert set(servers) == {"fakt_kb"}


def test_dispatch_default_includes_shared():
    assert "fakt_kb" in dispatch_mcp_servers(1, None, _Settings())


def test_dispatch_off_without_personal_is_none():
    assert dispatch_mcp_servers(1, None, _Settings(), include_shared=False) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kb_search", [False, True])
async def test_relay_passes_kb_search_to_bridge(kb_search):
    bus = EventBus()
    bridge = _Bridge()
    ClaudeEventRelay(
        bus=bus, claude_bridge=bridge, connections_store=_Connections(), settings=_Settings()
    )
    await bus.publish(
        UserMessageReceived(
            request_id="r", chat_id=1, user_id=42, topic_id=1, project_path="/tmp/p",
            text="hi", kb_search=kb_search,
        )
    )
    servers = bridge.calls[0]["mcp_servers"]
    assert set(servers) == ({"fakt_kb"} if kb_search else {"notion"})


def test_ws_kb_search_is_strictly_boolean_true(tmp_path):
    """Из WS в событие попадает только настоящее true; "true", 1 и отсутствие дают False."""
    import hashlib
    import hmac
    import time

    from starlette.testclient import TestClient

    from src.claude.session import SessionManager
    from src.config.settings import WebSettings
    from src.web.server import WebServer

    bus = EventBus()
    seen: list[bool] = []

    async def _capture(event: UserMessageReceived) -> None:
        seen.append(event.kb_search)

    bus.subscribe(UserMessageReceived, _capture)
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    project = tmp_path / "proj"
    project.mkdir()
    session = sm.create_session(
        topic_id=-1, project_path=str(project), project_name="proj", chat_id=100
    )
    server = WebServer(
        settings=WebSettings(
            enabled=True, host="127.0.0.1", port=0, jwt_secret="x" * 32,
            telegram_bot_username="t",
        ),
        allowed_user_ids=[100], bot_username="t", session_manager=sm, event_bus=bus,
        bot_token="12345:abc", jwt_secret="x" * 32, project_paths=[project],
    )
    payload = {"id": 100, "first_name": "A", "auth_date": int(time.time())}
    secret = hashlib.sha256(b"12345:abc").digest()
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    login = {**payload, "hash": hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()}
    cases = [{"kb_search": True}, {"kb_search": "true"}, {"kb_search": 1}, {}]
    try:
        with TestClient(server.app) as client:
            assert client.post("/api/auth/telegram", json=login).status_code == 200
            with client.websocket_connect(f"/api/ws/sessions/{session.session_uuid}") as ws:
                for i, extra in enumerate(cases):
                    ws.send_json({"type": "user_message", "text": f"m{i}", **extra})
                    for _ in range(100):
                        if len(seen) == i + 1:
                            break
                        time.sleep(0.02)
        assert seen == [True, False, False, False]
    finally:
        sm.close_sync()
        sm._engine.sync_engine.dispose()
