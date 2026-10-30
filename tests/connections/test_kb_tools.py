"""Инструменты базы знаний внутри процесса панели.

Сессия Claude не получает ни адреса, ни ключа: она видит только имена инструментов.
На сервер ходит панель, поэтому проверяем обе стороны: что уходит на сервер и что
возвращается модели. Все адреса и ключи здесь вымышленные.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import socket
from types import SimpleNamespace

import pytest
import structlog
from aiohttp import web
from aiohttp.test_utils import TestServer
from claude_agent_sdk._internal.sdk_mcp_bridge import SdkMcpBridge

from src.bot.middleware.security import _PATH_FIELDS
from src.claude.tool_firewall import firewall_check
from src.connections import kb_tools
from src.connections.kb_tools import KbEndpoint, build_kb_server, call_tool, url_allowed

KEY = "fake-upstream-key-0123456789"
TOOL_NAMES = (
    "search_project",
    "get_fragment",
    "trace_requirement",
    "list_related_tasks",
    "get_figma_mapping",
    "get_stand_routes",
    "aggregate_evidence",
)
VALID_ARGS = {
    "search_project": {"query": "отпуск"},
    "get_fragment": {"fragment_id": "ftt1.12"},
    "trace_requirement": {"requirement_id": "REQ-1"},
    "list_related_tasks": {"source_id": "REQ-1"},
    "get_figma_mapping": {"requirement_id": "REQ-1"},
    "get_stand_routes": {"source_id": "REQ-1"},
    "aggregate_evidence": {"question": "что с отпусками"},
}
SUPPORTED_VERSIONS = {
    "2025-11-25",
    "2026-07-28",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
    "2024-10-07",
}
HIDDEN_BODY = "тело-ошибки-сервера-не-показывать"


def _rpc(text: str = "marker", **result: object) -> dict:
    payload = {"content": [{"type": "text", "text": text}], **result}
    return {"jsonrpc": "2.0", "id": 1, "result": payload}


def _sse(message: dict) -> web.Response:
    """Ответ как у настоящего обработчика: один message в потоке событий."""
    body = f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
    return web.Response(text=body, content_type="text/event-stream")


class Upstream:
    """Фиктивный сервер: запоминает запросы, отвечает заданным ответом."""

    def __init__(self, respond=None) -> None:
        self.requests: list[SimpleNamespace] = []
        self.url = ""
        self._respond = respond

    async def handle(self, request: web.Request) -> web.StreamResponse:
        body = await request.read()
        self.requests.append(SimpleNamespace(headers=request.headers, body=body))
        if self._respond is None:
            return _sse(_rpc())
        result = self._respond(request)
        return await result if inspect.isawaitable(result) else result

    @property
    def endpoint(self) -> KbEndpoint:
        return KbEndpoint(url=self.url, key=KEY)

    @property
    def message(self) -> dict:
        return json.loads(self.requests[-1].body)


@pytest.fixture
async def start_upstream():
    servers: list[TestServer] = []

    async def _start(respond=None) -> Upstream:
        upstream = Upstream(respond)
        app = web.Application(client_max_size=1024 * 1024)
        app.router.add_post("/mcp", upstream.handle)
        server = TestServer(app)
        await server.start_server()
        servers.append(server)
        upstream.url = str(server.make_url("/mcp"))
        return upstream

    yield _start
    for server in servers:
        await server.close()


def _closed_port_url() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}/mcp"


def _text(result: dict) -> str:
    return "\n".join(item["text"] for item in result["content"])


async def _call(upstream: Upstream, name: str = "search_project", **arguments: object) -> dict:
    return await call_tool(upstream.endpoint, name, arguments or {"query": "q"}, user_id=7)


def _assert_error(result: dict, code: str) -> str:
    assert result["is_error"] is True
    text = _text(result)
    assert code in text
    assert "не ищи ответ в локальных файлах" in text.lower()
    assert KEY not in text
    return text


# --- Схемы --------------------------------------------------------------------


def test_exactly_seven_read_tools():
    assert tuple(tool.name for tool in kb_tools.TOOLS) == TOOL_NAMES


def test_server_name_gives_expected_tool_prefix():
    assert kb_tools.SERVER_NAME == "fakt_kb"


@pytest.mark.parametrize("spec", kb_tools.TOOLS, ids=lambda spec: spec.name)
def test_schema_is_closed_and_described(spec):
    assert spec.schema["type"] == "object"
    assert spec.schema["additionalProperties"] is False
    assert set(spec.schema["required"]) <= set(spec.schema["properties"])
    assert any("а" <= char <= "я" for char in spec.description.lower())


@pytest.mark.parametrize("spec", kb_tools.TOOLS, ids=lambda spec: spec.name)
def test_schema_has_no_profile_anywhere(spec):
    assert "profile" not in json.dumps(spec.schema)


@pytest.mark.parametrize("spec", kb_tools.TOOLS, ids=lambda spec: spec.name)
def test_schema_fields_are_not_firewall_paths(spec):
    """Поле path, file_path или directory файрвол confined-сессии счёл бы путём на диске."""
    assert not set(spec.schema["properties"]) & set(_PATH_FIELDS)


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_firewall_lets_tool_through_in_confined_session(name, tmp_path):
    tool_input = dict(VALID_ARGS[name])
    field = next(iter(tool_input))
    tool_input[field] = "/etc/passwd ../../.env"
    assert firewall_check(f"mcp__fakt_kb__{name}", tool_input, tmp_path) is None


@pytest.mark.parametrize(
    "name,field,key,value",
    [
        ("search_project", "query", "maxLength", 1000),
        ("search_project", "limit", "maximum", 20),
        ("search_project", "cursor", "maxLength", 1024),
        ("get_fragment", "fragment_id", "maxLength", 128),
        ("get_fragment", "fragment_id", "pattern", "^[A-Za-z0-9_.-]+$"),
        ("trace_requirement", "requirement_id", "maxLength", 128),
        ("list_related_tasks", "source_id", "maxLength", 128),
        ("list_related_tasks", "limit", "maximum", 20),
        ("aggregate_evidence", "question", "maxLength", 1000),
        ("aggregate_evidence", "max_sources", "maximum", 15),
    ],
)
def test_schema_limits_match_server(name, field, key, value):
    spec = next(tool for tool in kb_tools.TOOLS if tool.name == name)
    assert spec.schema["properties"][field][key] == value


@pytest.mark.parametrize(
    "name,field,values",
    [
        (
            "search_project",
            "scope",
            {"all", "documents", "requirements", "tasks", "matrix", "cases"},
        ),
        ("trace_requirement", "direction", {"forward", "reverse", "both"}),
        (
            "list_related_tasks",
            "relation",
            {
                "all",
                "requirements",
                "mentions",
                "redmine_relates",
                "candidate_origin",
                "package_context",
                "redmine_duplicates",
                "same_root_cause",
            },
        ),
    ],
)
def test_schema_enums_match_server(name, field, values):
    spec = next(tool for tool in kb_tools.TOOLS if tool.name == name)
    assert set(spec.schema["properties"][field]["enum"]) == values


# --- Сервер SDK: как его видит CLI ---------------------------------------------


async def _wire(server: dict, method: str, params: dict | None = None) -> dict:
    bridge = SdkMcpBridge(server["name"], server["instance"])
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
        return await bridge.handle(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        )
    finally:
        await bridge.aclose()


def test_build_kb_server_is_sdk_record():
    server = build_kb_server("https://kb.example.invalid/mcp", KEY)
    assert server["type"] == "sdk"
    assert server["name"] == "fakt_kb"
    assert KEY not in repr(server)
    assert "kb.example.invalid" not in repr(server)


async def test_wire_lists_seven_read_only_tools():
    server = build_kb_server("https://kb.example.invalid/mcp", KEY)
    response = await _wire(server, "tools/list")
    tools = response["result"]["tools"]
    assert tuple(tool["name"] for tool in tools) == TOOL_NAMES
    assert all(tool["annotations"]["readOnlyHint"] is True for tool in tools)
    assert "profile" not in json.dumps(tools)


async def test_wire_call_reaches_server_and_returns_marker(start_upstream):
    upstream = await start_upstream()
    server = build_kb_server(upstream.url, KEY, user_id=7)
    response = await _wire(
        server, "tools/call", {"name": "search_project", "arguments": {"query": "q"}}
    )
    assert "marker" in response["result"]["content"][0]["text"]
    assert not response["result"].get("isError")


async def test_wire_rejects_profile_before_server(start_upstream):
    upstream = await start_upstream()
    server = build_kb_server(upstream.url, KEY)
    response = await _wire(
        server,
        "tools/call",
        {"name": "search_project", "arguments": {"query": "q", "profile": "analyst"}},
    )
    assert response["result"]["isError"] is True
    assert upstream.requests == []


async def test_server_instance_works_for_a_second_query(start_upstream):
    """Повтор в bridge использует те же опции: один сервер на два запуска подряд."""
    upstream = await start_upstream()
    server = build_kb_server(upstream.url, KEY)
    params = {"name": "search_project", "arguments": {"query": "q"}}
    assert "marker" in (await _wire(server, "tools/call", params))["result"]["content"][0]["text"]
    assert "marker" in (await _wire(server, "tools/call", params))["result"]["content"][0]["text"]


# --- Запрос на сервер ----------------------------------------------------------


@pytest.mark.parametrize("name", TOOL_NAMES)
async def test_request_matches_protocol_gate(start_upstream, name):
    upstream = await start_upstream()
    await call_tool(upstream.endpoint, name, VALID_ARGS[name], user_id=1)

    seen = upstream.requests[-1].headers
    host = upstream.url.split("/")[2]
    assert seen["Host"] == host
    assert seen["Content-Type"].split(";")[0] == "application/json"
    assert seen["MCP-Protocol-Version"] in SUPPORTED_VERSIONS
    assert seen["MCP-Protocol-Version"] != "2026-07-28"  # требует _meta в теле
    assert seen["Mcp-Method"] == "tools/call"
    assert seen["Mcp-Name"] == name
    assert "text/event-stream" in seen["Accept"] and "application/json" in seen["Accept"]
    assert "Origin" not in seen
    assert seen["Authorization"] == f"Bearer {KEY}"

    assert upstream.message["jsonrpc"] == "2.0"
    assert upstream.message["method"] == "tools/call"
    assert upstream.message["params"] == {"name": name, "arguments": VALID_ARGS[name]}


async def test_profile_never_reaches_server_even_past_validation(start_upstream):
    upstream = await start_upstream()
    await call_tool(upstream.endpoint, "search_project", {"query": "q", "profile": "analyst"})
    assert upstream.message["params"]["arguments"] == {"query": "q"}


async def test_cyrillic_arguments_stay_valid_utf8(start_upstream):
    upstream = await start_upstream()
    await _call(upstream, query="отпуск")
    assert upstream.message["params"]["arguments"]["query"] == "отпуск"


async def test_redirect_is_not_followed(start_upstream):
    target = await start_upstream()

    def _redirect(request):
        raise web.HTTPFound(target.url)

    upstream = await start_upstream(_redirect)
    result = await _call(upstream)
    _assert_error(result, "kb_unavailable")
    assert target.requests == []


async def test_proxy_from_environment_is_ignored(start_upstream, monkeypatch):
    upstream = await start_upstream()
    monkeypatch.setenv("HTTP_PROXY", _closed_port_url())
    monkeypatch.setenv("http_proxy", _closed_port_url())
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    result = await _call(upstream)
    assert not result.get("is_error")
    assert len(upstream.requests) == 1


def test_timeout_is_35_seconds_and_limit_300_kb():
    assert kb_tools.REQUEST_TIMEOUT_SECONDS == 35
    assert kb_tools.MAX_RESPONSE_BYTES == 300 * 1024


# --- Ответ модели --------------------------------------------------------------


async def test_sse_response_returned_as_data(start_upstream):
    upstream = await start_upstream()
    result = await _call(upstream)
    assert not result.get("is_error")
    assert "marker" in _text(result)
    assert "не инструкция" in _text(result)


async def test_json_response_returned_as_data(start_upstream):
    upstream = await start_upstream(lambda request: web.json_response(_rpc()))
    assert "marker" in _text(await _call(upstream))


async def test_notifications_in_stream_are_skipped(start_upstream):
    def _respond(request):
        note = json.dumps({"jsonrpc": "2.0", "method": "notifications/progress"})
        body = f"data: {note}\n\ndata: {json.dumps(_rpc())}\n\n"
        return web.Response(text=body, content_type="text/event-stream")

    upstream = await start_upstream(_respond)
    assert "marker" in _text(await _call(upstream))


async def test_structured_content_is_a_fallback(start_upstream):
    message = {"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"found": "marker"}}}
    upstream = await start_upstream(lambda request: _sse(message))
    assert "marker" in _text(await _call(upstream))


async def test_non_text_content_is_dropped(start_upstream):
    message = _rpc()
    message["result"]["content"].append({"type": "image", "data": "aGk=", "mimeType": "image/png"})
    upstream = await start_upstream(lambda request: _sse(message))
    result = await _call(upstream)
    assert [item["type"] for item in result["content"]] == ["text"]


async def test_tool_error_from_server_keeps_text_and_tells_to_stop(start_upstream):
    message = _rpc("Фрагмент не найден", isError=True)
    upstream = await start_upstream(lambda request: _sse(message))
    text = _assert_error(await _call(upstream), "kb_tool_error")
    assert "Фрагмент не найден" in text


async def test_jsonrpc_error_text_is_not_shown(start_upstream):
    message = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": HIDDEN_BODY}}
    upstream = await start_upstream(lambda request: _sse(message))
    text = _assert_error(await _call(upstream), "kb_rejected")
    assert HIDDEN_BODY not in text


@pytest.mark.parametrize(
    "status,code,phrase",
    [
        (401, "kb_auth", "ключ не принят"),
        (403, "kb_auth", "ключ не принят"),
        (400, "kb_rejected", "отклонила"),
        (404, "kb_rejected", "отклонила"),
        (413, "kb_rejected", "отклонила"),
        (421, "kb_rejected", "отклонила"),
        (500, "kb_unavailable", "недоступна"),
        (502, "kb_unavailable", "недоступна"),
        (503, "kb_unavailable", "недоступна"),
        (504, "kb_unavailable", "недоступна"),
    ],
)
async def test_error_status_hides_body(start_upstream, status, code, phrase):
    upstream = await start_upstream(lambda request: web.Response(status=status, text=HIDDEN_BODY))
    text = _assert_error(await _call(upstream), code)
    assert phrase in text
    assert HIDDEN_BODY not in text


async def test_rate_limit_names_seconds(start_upstream):
    upstream = await start_upstream(
        lambda request: web.Response(status=429, headers={"Retry-After": "17"})
    )
    text = _assert_error(await _call(upstream), "kb_rate_limited")
    assert "Превышен лимит запросов" in text
    assert "17" in text


@pytest.mark.parametrize(
    "headers",
    [{}, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, {"Retry-After": "soon"}],
    ids=["no-header", "date", "garbage"],
)
async def test_rate_limit_without_seconds(start_upstream, headers):
    upstream = await start_upstream(lambda request: web.Response(status=429, headers=headers))
    text = _assert_error(await _call(upstream), "kb_rate_limited")
    assert "None" not in text
    assert "soon" not in text


@pytest.mark.parametrize("status", [200, 401, 500])
@pytest.mark.parametrize(
    "payload",
    [KEY.encode(), json.dumps(_rpc(f"утёк {KEY}")).encode()],
    ids=["raw", "in-text"],
)
async def test_key_in_any_response_is_an_error(start_upstream, payload, status):
    upstream = await start_upstream(
        lambda request: web.Response(status=status, body=payload, content_type="application/json")
    )
    _assert_error(await _call(upstream), "kb_unsafe_response")


async def test_json_escaped_key_is_an_error(start_upstream):
    """В сыром теле байт ключа нет, он появляется после разбора JSON."""
    escaped = "".join(f"\\u{ord(char):04x}" for char in KEY)
    body = '{"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"%s"}]}}' % escaped
    upstream = await start_upstream(
        lambda request: web.Response(text=body, content_type="application/json")
    )
    _assert_error(await _call(upstream), "kb_unsafe_response")


async def test_key_in_sse_response_is_an_error(start_upstream):
    upstream = await start_upstream(lambda request: _sse(_rpc(f"утёк {KEY}")))
    _assert_error(await _call(upstream), "kb_unsafe_response")


@pytest.mark.parametrize(
    "respond",
    [
        lambda request: web.Response(text="<html>не json</html>", content_type="text/html"),
        lambda request: web.Response(status=200),
        lambda request: web.Response(status=202),
        lambda request: web.Response(text="data: {oops\n\n", content_type="text/event-stream"),
        lambda request: web.Response(body=b"\xff\xfe", content_type="application/json"),
        lambda request: web.json_response([1, 2]),
        lambda request: web.json_response({"jsonrpc": "2.0", "id": 1, "result": {"content": []}}),
    ],
    ids=["html", "empty", "202", "broken-sse", "bad-utf8", "array", "no-content"],
)
async def test_unreadable_response_is_an_error(start_upstream, respond):
    upstream = await start_upstream(respond)
    _assert_error(await _call(upstream), "kb_bad_response")


async def test_response_over_limit_is_an_error(start_upstream, monkeypatch):
    monkeypatch.setattr(kb_tools, "MAX_RESPONSE_BYTES", 2048)
    upstream = await start_upstream(lambda request: web.Response(body=b"x" * 2049))
    _assert_error(await _call(upstream), "kb_too_large")


async def test_response_at_limit_passes(start_upstream, monkeypatch):
    body = _sse(_rpc("marker")).text.encode()
    monkeypatch.setattr(kb_tools, "MAX_RESPONSE_BYTES", len(body))
    upstream = await start_upstream(lambda request: _sse(_rpc("marker")))
    assert "marker" in _text(await _call(upstream))


async def test_network_error_has_no_address():
    endpoint = KbEndpoint(url=_closed_port_url(), key=KEY)
    result = await call_tool(endpoint, "search_project", {"query": "q"})
    text = _assert_error(result, "kb_unavailable")
    assert "127.0.0.1" not in text


async def test_timeout_is_an_error(start_upstream, monkeypatch):
    async def _hang(request):
        await asyncio.sleep(5)
        return web.Response()

    monkeypatch.setattr(kb_tools, "REQUEST_TIMEOUT_SECONDS", 0.05)
    upstream = await start_upstream(_hang)
    _assert_error(await _call(upstream), "kb_timeout")


async def test_slow_drip_hits_total_deadline(start_upstream, monkeypatch):
    async def _drip(request):
        response = web.StreamResponse()
        await response.prepare(request)
        for _ in range(100):
            await response.write(b"x")
            await asyncio.sleep(0.02)
        return response

    monkeypatch.setattr(kb_tools, "REQUEST_TIMEOUT_SECONDS", 0.1)
    upstream = await start_upstream(_drip)
    _assert_error(await _call(upstream), "kb_timeout")


async def test_unexpected_exception_text_is_not_shown(monkeypatch):
    """Текст исключения SDK показал бы модели, а в нём бывает адрес сервера."""

    async def _boom(*args, **kwargs):
        raise RuntimeError(f"сломалось на https://kb.example.invalid {KEY}")

    monkeypatch.setattr(kb_tools, "_post", _boom)
    endpoint = KbEndpoint(url="https://kb.example.invalid/mcp", key=KEY)
    result = await call_tool(endpoint, "search_project", {"query": "q"})
    text = _assert_error(result, "kb_unavailable")
    assert "kb.example.invalid" not in text


# --- Логи ----------------------------------------------------------------------


async def test_log_has_user_tool_status_duration(start_upstream):
    upstream = await start_upstream()
    with structlog.testing.capture_logs() as logs:
        await _call(upstream, query="секретный вопрос")
    entry = next(item for item in logs if item["event"] == "kb_tool_call")
    assert entry["user_id"] == 7
    assert entry["tool"] == "search_project"
    assert entry["status"] == 200
    assert entry["duration_ms"] >= 0


@pytest.mark.parametrize("case", ["ok", "401", "network", "timeout", "key-in-body"])
async def test_logs_hold_no_key_url_or_query(start_upstream, monkeypatch, caplog, capsys, case):
    query = "секретный вопрос пользователя"
    if case == "network":
        endpoint = KbEndpoint(url=_closed_port_url(), key=KEY)
    else:
        responses = {
            "ok": lambda request: _sse(_rpc("marker")),
            "401": lambda request: web.Response(status=401, text=HIDDEN_BODY),
            "key-in-body": lambda request: web.Response(text=KEY),
        }

        async def _hang(request):
            await asyncio.sleep(5)
            return web.Response()

        if case == "timeout":
            monkeypatch.setattr(kb_tools, "REQUEST_TIMEOUT_SECONDS", 0.05)
        upstream = await start_upstream(responses.get(case, _hang))
        endpoint = upstream.endpoint

    with caplog.at_level(logging.DEBUG), structlog.testing.capture_logs() as logs:
        await call_tool(endpoint, "search_project", {"query": query}, user_id=7)

    captured = capsys.readouterr()
    dumped = repr(logs) + caplog.text + captured.out + captured.err
    assert any(item["event"] == "kb_tool_call" for item in logs)
    host_and_port = endpoint.url.split("/")[2]
    for forbidden in (KEY, query, host_and_port, HIDDEN_BODY):
        assert forbidden not in dumped


def test_endpoint_repr_hides_url_and_key():
    dumped = repr(KbEndpoint(url="https://kb.example.invalid/mcp", key=KEY))
    assert KEY not in dumped
    assert "kb.example.invalid" not in dumped


# --- Адрес сервера -------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://kb.example.invalid/mcp",
        "HTTPS://kb.example.invalid/mcp",
        "https://kb.example.invalid:8443/mcp",
        "http://127.0.0.1:9090/mcp",
        "http://localhost:9090/mcp",
        "http://[::1]:9090/mcp",
    ],
)
def test_url_allowed(url):
    assert url_allowed(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "",
        "kb.example.invalid/mcp",
        "http://kb.example.invalid/mcp",
        "http://127.0.0.1.evil.invalid/mcp",
        "http://127.0.0.1@evil.invalid/mcp",
        "http://localhost:80@evil.invalid/mcp",
        "https://user:pass@kb.example.invalid/mcp",
        "https:///mcp",
        "ftp://kb.example.invalid/mcp",
        "file:///etc/passwd",
        "http://[::1/mcp",
    ],
)
def test_url_rejected(url):
    assert url_allowed(url) is False
