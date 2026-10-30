"""Прокси личных подключений: сервер MCP в процессе панели.

Claude видит только имя и тип записи. Токен остаётся в панели: прокси сам открывает
сессию с настоящим сервисом на каждый запрос и закрывает её в той же задаче.
Сервер проверяется так, как его видит CLI: через SdkMcpBridge из claude-agent-sdk.
"""
from __future__ import annotations

import json
import logging
import sys

import pytest
import structlog
from claude_agent_sdk._internal.sdk_mcp_bridge import SdkMcpBridge

from src.child_env import ALLOWED_NAMES, ALLOWED_PREFIXES
from src.connections import proxy
from tests.connections.fake_upstream import (
    GITHUB_TOKEN,
    MARKER,
    NOTION_TOKEN,
    STDIO_MARKER,
    TOOL_TITLE,
    github_config,
    notion_config,
    serve_fake_github,
    token_digest,
)
from tests.spawn_audit import allowing_names, spawn_audit  # noqa: F401

pytestmark = pytest.mark.usefixtures("spawn_audit")

WRONG_TOKEN = "ghp_FAKE_WRONG_TOKEN_999"
PARENT_SECRETS = {
    "KB_MCP_KEY": "fake-kb-key-proxy-0123",
    "CONNECTIONS_SECRET_KEY": "fake-connections-proxy-0123",
    "MY_NEW_SERVICE_SECRET": "fake-new-service-proxy-0123",
}


@pytest.fixture(autouse=True)
def _fresh_cache():
    proxy.clear_tools_cache()
    yield
    proxy.clear_tools_cache()


@pytest.fixture
async def github():
    async with serve_fake_github() as fake:
        yield fake


class Wire:
    """JSON-RPC так, как его шлёт CLI в сервер типа sdk."""

    def __init__(self, entry: dict) -> None:
        self.bridge = SdkMcpBridge(entry["name"], entry["instance"])
        self._id = 0

    async def request(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        return await self.bridge.handle(
            {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        )

    async def __aenter__(self) -> Wire:
        await self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        await self.bridge.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    async def __aexit__(self, *exc) -> None:
        await self.bridge.aclose()

    async def call(self, name: str, arguments: dict | None = None) -> dict:
        return (await self.request("tools/call", {"name": name, "arguments": arguments or {}}))[
            "result"
        ]


def _text(result: dict) -> str:
    return "".join(block.get("text", "") for block in result["content"])


def _assert_no_secret(*blobs: str, secrets=(GITHUB_TOKEN, WRONG_TOKEN, NOTION_TOKEN)) -> None:
    for blob in blobs:
        for secret in secrets:
            assert secret not in blob


# --- Запись для SDK -------------------------------------------------------------


def test_record_is_sdk_and_hides_token():
    entry = proxy.build_proxy_server("github", github_config("https://example.invalid/mcp"))
    assert entry["type"] == "sdk"
    assert entry["name"] == "github"
    assert entry["instance"] is not None
    assert GITHUB_TOKEN not in repr(entry)
    assert GITHUB_TOKEN not in repr(vars(entry["instance"]))


def test_record_server_name_is_service_id():
    entry = proxy.build_proxy_server("notion", notion_config())
    assert entry["instance"].name == "notion"


@pytest.mark.parametrize(
    "config",
    [{}, {"type": "http"}, {"type": "http", "url": "ftp://x"}, {"command": ""}, {"type": "sse"}],
    ids=["empty", "http-no-url", "http-bad-scheme", "stdio-no-command", "unknown-type"],
)
def test_bad_config_is_rejected_at_build(config):
    with pytest.raises(ValueError):
        proxy.build_proxy_server("x", config)


def test_bad_config_error_has_no_secret():
    config = {"type": "sse", "headers": {"Authorization": f"Bearer {GITHUB_TOKEN}"}}
    with pytest.raises(ValueError) as info:
        proxy.build_proxy_server("github", config)
    _assert_no_secret(str(info.value), repr(info.value))


# --- HTTP: как удалённый GitHub MCP ---------------------------------------------


async def test_http_lists_upstream_tools_with_annotations(github):
    entry = proxy.build_proxy_server("github", github_config(github.url))
    async with Wire(entry) as wire:
        tools = (await wire.request("tools/list"))["result"]["tools"]
    by_name = {tool["name"]: tool for tool in tools}
    assert set(by_name) == {"get_me", "add"}
    assert by_name["get_me"]["annotations"]["readOnlyHint"] is True
    assert by_name["get_me"]["annotations"]["title"] == TOOL_TITLE
    assert by_name["add"]["inputSchema"]["required"] == ["a", "b"]
    assert github.rejected == []


async def test_http_call_returns_upstream_content(github):
    entry = proxy.build_proxy_server("github", github_config(github.url))
    async with Wire(entry) as wire:
        result = await wire.call("get_me")
        summed = await wire.call("add", {"a": 2, "b": 3})
    assert not result.get("isError")
    assert MARKER in _text(result)
    assert _text(summed) == "5"
    assert github.rejected == []


async def test_http_tools_list_is_cached(github):
    entry = proxy.build_proxy_server("github", github_config(github.url))
    async with Wire(entry) as wire:
        await wire.request("tools/list")
        seen = github.accepted
        await wire.request("tools/list")
    second = proxy.build_proxy_server("github", github_config(github.url))
    async with Wire(second) as wire:
        tools = (await wire.request("tools/list"))["result"]["tools"]
    assert github.accepted == seen
    assert {tool["name"] for tool in tools} == {"get_me", "add"}


async def test_http_cache_is_per_token(github):
    """Другой токен того же сервиса не получает чужой список из кеша."""
    good = proxy.build_proxy_server("github", github_config(github.url))
    async with Wire(good) as wire:
        await wire.request("tools/list")
    bad = proxy.build_proxy_server("github", github_config(github.url, WRONG_TOKEN))
    async with Wire(bad) as wire:
        response = await wire.request("tools/list")
    assert "error" in response
    assert github.rejected


@pytest.mark.parametrize("token", [WRONG_TOKEN, None], ids=["wrong-token", "no-header"])
async def test_http_upstream_rejects_bad_header_and_result_is_safe(
    github, token, caplog, capsys
):
    entry = proxy.build_proxy_server("github", github_config(github.url, token))
    with caplog.at_level(logging.DEBUG), structlog.testing.capture_logs() as logs:
        async with Wire(entry) as wire:
            result = await wire.call("get_me")
            listed = await wire.request("tools/list")
    assert github.rejected, "сервис должен был отказать"
    assert result["isError"] is True
    text = _text(result)
    assert "401" in text
    assert "github" in text
    assert "error" in listed and "401" in listed["error"]["message"]
    captured = capsys.readouterr()
    _assert_no_secret(
        json.dumps(result), json.dumps(listed), repr(logs), caplog.text, captured.out + captured.err
    )
    assert github.url not in json.dumps(result) + json.dumps(listed)
    failures = [entry for entry in logs if entry["event"] == "connection_proxy_failed"]
    assert failures
    assert {entry["service_id"] for entry in failures} == {"github"}
    assert all(entry.get("http_status") == 401 for entry in failures)


async def test_http_unreachable_upstream_is_safe(caplog):
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()  # порт свободен: соединение получит отказ
    url = f"http://127.0.0.1:{port}/mcp"
    entry = proxy.build_proxy_server("github", github_config(url))
    with structlog.testing.capture_logs() as logs:
        async with Wire(entry) as wire:
            result = await wire.call("get_me")
    assert result["isError"] is True
    _assert_no_secret(json.dumps(result), repr(logs), caplog.text)
    assert url not in json.dumps(result)


async def test_call_timeout_is_safe(monkeypatch, caplog):
    """Сервис не отвечает: прокси сдаётся по таймауту и не держит запрос вечно."""
    monkeypatch.setattr(proxy, "CALL_TIMEOUT_SECONDS", 1.0)
    hang = {
        "command": sys.executable,
        "args": ["-c", "import time; time.sleep(30)"],
        "env": {"NOTION_TOKEN": NOTION_TOKEN},
    }
    entry = proxy.build_proxy_server("notion", hang)
    with allowing_names("NOTION_TOKEN"), structlog.testing.capture_logs() as logs:
        async with Wire(entry) as wire:
            result = await wire.call("env_report")
    assert result["isError"] is True
    assert "TimeoutError" in _text(result)
    _assert_no_secret(json.dumps(result), repr(logs), caplog.text)


# --- stdio: как npx-сервер Notion -----------------------------------------------


async def test_stdio_env_has_token_and_nothing_outside_allowlist(monkeypatch):
    for name, value in PARENT_SECRETS.items():
        monkeypatch.setenv(name, value)
    entry = proxy.build_proxy_server("notion", notion_config())
    with allowing_names("NOTION_TOKEN"):
        async with Wire(entry) as wire:
            tools = (await wire.request("tools/list"))["result"]["tools"]
            result = await wire.call("env_report")
    assert [tool["name"] for tool in tools] == ["env_report"]
    assert tools[0]["annotations"]["readOnlyHint"] is True
    assert not result.get("isError")
    report = json.loads(_text(result))
    assert report["marker"] == STDIO_MARKER
    assert report["token_sha256"] == token_digest(NOTION_TOKEN)
    names = set(report["names"])
    assert "NOTION_TOKEN" in names
    assert not names & set(PARENT_SECRETS)
    # macOS сам добавляет служебную переменную в любой процесс; значение не секрет.
    extra = {
        name
        for name in names - ALLOWED_NAMES - {"NOTION_TOKEN", "__CF_USER_TEXT_ENCODING"}
        if not name.startswith(ALLOWED_PREFIXES)
    }
    assert not extra


def test_stdio_env_is_built_from_allowlist(monkeypatch):
    for name, value in PARENT_SECRETS.items():
        monkeypatch.setenv(name, value)
    params = proxy._stdio_parameters(notion_config())
    assert params.env["NOTION_TOKEN"] == NOTION_TOKEN
    assert not set(params.env) & set(PARENT_SECRETS)
    assert set(params.env) - {"NOTION_TOKEN"} <= {
        name for name in params.env if name in ALLOWED_NAMES or name.startswith(ALLOWED_PREFIXES)
    }


async def test_stdio_spawn_failure_is_safe(caplog, capsys):
    config = {
        "command": "/nonexistent/ai-workspace-no-such-binary",
        "args": [],
        "env": {"NOTION_TOKEN": NOTION_TOKEN},
    }
    entry = proxy.build_proxy_server("notion", config)
    with (
        allowing_names("NOTION_TOKEN"),
        caplog.at_level(logging.DEBUG),
        structlog.testing.capture_logs() as logs,
    ):
        async with Wire(entry) as wire:
            result = await wire.call("env_report")
            listed = await wire.request("tools/list")
    assert result["isError"] is True
    assert "notion" in _text(result)
    assert "error" in listed
    captured = capsys.readouterr()
    _assert_no_secret(
        json.dumps(result), json.dumps(listed), repr(logs), caplog.text, captured.out + captured.err
    )
    assert any(entry["event"] == "connection_proxy_failed" for entry in logs)


def test_safe_message_never_uses_exception_text():
    exc = RuntimeError(f"Authorization: Bearer {GITHUB_TOKEN} at https://x.invalid/?t=1")
    message = proxy._safe_message("github", exc)
    _assert_no_secret(message)
    assert "x.invalid" not in message
    assert "RuntimeError" in message


def test_safe_message_unwraps_groups_and_finds_status():
    import httpx2

    request = httpx2.Request("POST", f"https://u:{GITHUB_TOKEN}@x.invalid/mcp")
    response = httpx2.Response(403, request=request)
    error = httpx2.HTTPStatusError(f"bad {GITHUB_TOKEN}", request=request, response=response)
    group = ExceptionGroup("outer", [ExceptionGroup("inner", [error])])
    message = proxy._safe_message("github", group)
    assert "403" in message
    assert "HTTPStatusError" in message
    _assert_no_secret(message)
