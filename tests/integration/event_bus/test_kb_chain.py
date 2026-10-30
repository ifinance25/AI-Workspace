"""Цепочка лупы: событие, релей, мост, настоящие опции SDK, настоящие argv.

Подменён только сам запуск claude. Опции собирает настоящий _build_sdk_options с
настоящим ClaudeAgentOptions, аргументы строит настоящий SubprocessCLITransport, а
инструмент вызывается через тот же мост MCP, что и в SDK.
"""
from __future__ import annotations

import dataclasses
import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk._internal.sdk_mcp_bridge import SdkMcpBridge
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

from src.claude.bridge import ClaudeBridge
from src.config.settings import Settings
from src.event_bus import ClaudeEventRelay, EventBus
from src.event_bus.events import UserMessageReceived

KB_KEY = "fake-kb-key-0123456789"
MARKER = "маркер-базы-знаний-7316"


@pytest.fixture
async def upstream_url():
    async def _handle(request: web.Request) -> web.Response:
        assert request.headers["Authorization"] == f"Bearer {KB_KEY}"
        body = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": MARKER}]},
        }
        return web.Response(
            text=f"data: {json.dumps(body, ensure_ascii=False)}\n\n",
            content_type="text/event-stream",
        )

    app = web.Application()
    app.router.add_post("/mcp", _handle)
    server = TestServer(app)
    await server.start_server()
    yield str(server.make_url("/mcp"))
    await server.close()


@pytest.fixture
def run_chain(monkeypatch, tmp_path):
    async def _run(url: str, *, kb_search: bool, transport: str = "sdk") -> dict:
        monkeypatch.setenv("KB_MCP_URL", url)
        monkeypatch.setenv("KB_MCP_KEY", KB_KEY)
        settings = Settings(_env_file=None)
        settings.claude.transport = transport

        captured: dict = {}

        async def _fake_query(*, prompt, options):
            captured["options"] = options
            located = dataclasses.replace(options, cli_path="/bin/true")
            transport = SubprocessCLITransport(prompt=prompt, options=located)
            captured["argv"] = transport._build_command()
            return
            yield

        monkeypatch.setattr(
            "src.claude.bridge._load_sdk", lambda: (ClaudeAgentOptions, _fake_query)
        )
        bus = EventBus()
        ClaudeEventRelay(bus=bus, claude_bridge=ClaudeBridge(), settings=settings)
        await bus.publish(
            UserMessageReceived(
                request_id="r",
                chat_id=1,
                user_id=42,
                topic_id=1,
                project_path=str(tmp_path),
                text="hi",
                kb_search=kb_search,
            )
        )
        return captured

    return _run


async def test_kb_search_on_reaches_sdk_process_arguments(run_chain, upstream_url):
    captured = await run_chain(upstream_url, kb_search=True)
    argv = captured["argv"]
    joined = " ".join(argv)
    assert KB_KEY not in joined
    assert upstream_url not in joined
    assert "127.0.0.1" not in joined
    config = json.loads(argv[argv.index("--mcp-config") + 1])
    assert config == {"mcpServers": {"fakt_kb": {"type": "sdk", "name": "fakt_kb"}}}
    assert argv[argv.index("--allowedTools") + 1] == "mcp__fakt_kb__*"
    assert "mcp__fakt_kb__" in captured["options"].system_prompt["append"]


async def test_kb_search_on_tool_answers_through_sdk_bridge(run_chain, upstream_url):
    captured = await run_chain(upstream_url, kb_search=True)
    server = captured["options"].mcp_servers["fakt_kb"]
    bridge = SdkMcpBridge("fakt_kb", server["instance"])
    try:
        await bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 0,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            }
        )
        await bridge.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        response = await bridge.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "search_project", "arguments": {"query": "q"}},
            }
        )
    finally:
        await bridge.aclose()
    assert MARKER in response["result"]["content"][0]["text"]


async def test_kb_search_off_leaves_no_trace(run_chain, upstream_url):
    captured = await run_chain(upstream_url, kb_search=False)
    argv = captured["argv"]
    assert "--mcp-config" not in argv
    assert "--allowedTools" not in argv
    assert "mcp__fakt_kb__" not in captured["options"].system_prompt["append"]


async def test_transport_other_than_sdk_gets_no_kb(run_chain, upstream_url):
    captured = await run_chain(upstream_url, kb_search=True, transport="cli")
    assert "--mcp-config" not in captured["argv"]
