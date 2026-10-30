"""Личные подключения как MCP-серверы в процессе панели.

Раньше запись сервиса (адрес и заголовок Authorization у GitHub, NOTION_TOKEN у Notion)
уходила в claude целиком: SDK кладёт mcp_servers в аргумент --mcp-config, а его видит
любой процесс машины через ps. Теперь claude получает запись типа sdk: только имя и тип.
Токен остаётся здесь, а к сервису ходит панель.

На каждый запрос прокси открывает сессию с сервисом и закрывает её в той же задаче:
отменяющие области anyio ломаются, если контекст открыт в одной задаче, а закрыт в другой.
Список инструментов кешируется по сервису и токену.

Ошибка сервиса превращается в короткий безопасный текст: класс исключения и код HTTP.
Текст исключения не идёт ни модели, ни в журнал: в нём может оказаться заголовок,
адрес с данными входа или окружение процесса.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AsyncExitStack
from typing import Any, TypeVar
from urllib.parse import urlsplit

import anyio
import structlog

from src.child_env import connection_env

logger = structlog.get_logger()

_T = TypeVar("_T")

SERVER_VERSION = "1.0.0"
# Первый запуск npx скачивает пакет: список инструментов ждёт дольше.
LIST_TIMEOUT_SECONDS = 90.0
CALL_TIMEOUT_SECONDS = 120.0
HTTP_CONNECT_TIMEOUT_SECONDS = 15.0
TOOLS_CACHE_TTL_SECONDS = 600.0
_MAX_TOOL_PAGES = 20
_TOKEN_STATUSES = frozenset({401, 403})

# Ключ: отпечаток сервиса и всей его записи (с токеном), значение: (время, инструменты).
_tools_cache: dict[str, tuple[float, list[Any]]] = {}


def clear_tools_cache() -> None:
    _tools_cache.clear()


def supported() -> bool:
    """Прокси написан под mcp 2.x: на 1.x другой API клиента и сервера."""
    try:
        import mcp.types
    except ImportError:
        return False
    return hasattr(mcp.types, "jsonrpc_message_adapter")


class UpstreamError(Exception):
    """Сбой сервиса: только класс исходного исключения и коды, без его текста."""

    def __init__(self, error_class: str, http_status: int | None, rpc_code: int | None) -> None:
        super().__init__(error_class)
        self.error_class = error_class
        self.http_status = http_status
        self.rpc_code = rpc_code


class _Upstream:
    """Как дойти до настоящего сервиса. Запись с токеном в repr не попадает."""

    __slots__ = ("service_id", "_config", "_cache_key")

    def __init__(self, service_id: str, config: Mapping[str, Any]) -> None:
        kind = config.get("type", "stdio")
        if kind == "http":
            url = config.get("url")
            parts = urlsplit(url) if isinstance(url, str) else None
            if parts is None or parts.scheme not in ("http", "https") or not parts.netloc:
                raise ValueError("подключение http без корректного адреса")
            headers = config.get("headers") or {}
            if not isinstance(headers, Mapping):
                raise ValueError("заголовки подключения должны быть словарём")
        elif kind == "stdio":
            command = config.get("command")
            if not isinstance(command, str) or not command:
                raise ValueError("подключение stdio без команды")
            if not isinstance(config.get("args") or [], list):
                raise ValueError("аргументы подключения должны быть списком")
            if not isinstance(config.get("env") or {}, Mapping):
                raise ValueError("окружение подключения должно быть словарём")
        else:
            raise ValueError("неподдерживаемый тип подключения")
        self.service_id = service_id
        self._config = dict(config)
        digest = hashlib.sha256(
            json.dumps([service_id, self._config], sort_keys=True, default=str).encode()
        )
        self._cache_key = digest.hexdigest()

    def __repr__(self) -> str:
        return f"<connection upstream {self.service_id}>"

    @property
    def is_http(self) -> bool:
        return self._config.get("type") == "http"

    async def _with_client(self, action: Callable[[Any], Awaitable[_T]], timeout: float) -> _T:
        """Открыть сессию, выполнить action и закрыть всё в этой же задаче.

        Любой сбой выходит как UpstreamError без текста исходного исключения.
        """
        statuses: list[int] = []
        try:
            with anyio.fail_after(timeout):
                async with AsyncExitStack() as stack:
                    transport = await self._transport(stack, statuses)
                    from mcp.client import Client

                    client = await stack.enter_async_context(
                        Client(transport, mode="legacy", cache=None)
                    )
                    return await action(client)
        except Exception as exc:  # noqa: BLE001 — дальше идёт только класс и коды
            error_class, status, rpc_code = _describe(exc)
            # Клиент mcp превращает ответ 401 в общую ошибку JSON-RPC: код берём из ответа.
            status = status if status is not None else (statuses[-1] if statuses else None)
            raise UpstreamError(error_class, status, rpc_code) from None

    async def _transport(self, stack: AsyncExitStack, statuses: list[int]) -> Any:
        if self.is_http:
            import httpx2
            from mcp.client.streamable_http import streamable_http_client

            async def record(response: Any) -> None:
                if response.status_code >= 400:
                    statuses.append(response.status_code)

            http = await stack.enter_async_context(
                httpx2.AsyncClient(
                    headers=dict(self._config.get("headers") or {}),
                    timeout=httpx2.Timeout(HTTP_CONNECT_TIMEOUT_SECONDS, read=CALL_TIMEOUT_SECONDS),
                    event_hooks={"response": [record]},
                )
            )
            return streamable_http_client(self._config["url"], http_client=http)
        from mcp.client.stdio import stdio_client

        # stderr сервиса не идёт в журнал панели: там мог бы оказаться токен.
        errlog = stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
        return stdio_client(_stdio_parameters(self._config), errlog=errlog)

    async def list_tools(self) -> list[Any]:
        cached = _tools_cache.get(self._cache_key)
        if cached and time.monotonic() - cached[0] < TOOLS_CACHE_TTL_SECONDS:
            return cached[1]

        async def fetch(client: Any) -> list[Any]:
            tools: list[Any] = []
            cursor: str | None = None
            for _ in range(_MAX_TOOL_PAGES):
                page = await client.list_tools(cursor=cursor)
                tools.extend(page.tools)
                cursor = page.next_cursor
                if not cursor:
                    break
            return tools

        tools = await self._with_client(fetch, LIST_TIMEOUT_SECONDS)
        _tools_cache[self._cache_key] = (time.monotonic(), tools)
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        async def call(client: Any) -> Any:
            return await client.call_tool(name, arguments)

        return await self._with_client(call, CALL_TIMEOUT_SECONDS)


def _stdio_parameters(config: Mapping[str, Any]) -> Any:
    """Запуск stdio-сервиса: белый список панели плюс только его собственные переменные."""
    from mcp.client.stdio import StdioServerParameters

    return StdioServerParameters(
        command=config["command"],
        args=[str(arg) for arg in config.get("args") or []],
        env=connection_env(config.get("env") or {}),
    )


def _leaves(exc: BaseException) -> list[BaseException]:
    group = getattr(exc, "exceptions", None)
    if isinstance(exc, BaseExceptionGroup) and group:
        return [leaf for inner in group for leaf in _leaves(inner)]
    return [exc]


def _http_status(exc: BaseException) -> int | None:
    """Код HTTP из исключения или его причин, без чтения текста."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            return status
        current = current.__cause__ or current.__context__
    return None


def _describe(exc: BaseException) -> tuple[str, int | None, int | None]:
    """Класс исключения, код HTTP и код JSON-RPC: всё, что безопасно показать."""
    if isinstance(exc, UpstreamError):
        return exc.error_class, exc.http_status, exc.rpc_code
    leaves = _leaves(exc)
    leaf = next((item for item in leaves if _http_status(item) is not None), leaves[0])
    code = getattr(leaf, "code", None)
    rpc_code = code if type(leaf).__name__ == "MCPError" and isinstance(code, int) else None
    return type(leaf).__name__, _http_status(leaf), rpc_code


def _safe_message(service_id: str, exc: BaseException) -> str:
    error_class, status, rpc_code = _describe(exc)
    details = [error_class]
    if status is not None:
        details.append(f"HTTP {status}")
    if rpc_code is not None:
        details.append(f"код {rpc_code}")
    message = f"Сервис {service_id} не ответил ({', '.join(details)})."
    if status in _TOKEN_STATUSES:
        message += " Проверьте токен в разделе «Подключения»."
    return message


def _log_failure(service_id: str, operation: str, exc: BaseException) -> None:
    error_class, status, rpc_code = _describe(exc)
    logger.warning(
        "connection_proxy_failed",
        service_id=service_id,
        operation=operation,
        error_class=error_class,
        http_status=status,
        rpc_code=rpc_code,
    )


def build_proxy_server(service_id: str, config: Mapping[str, Any]) -> dict[str, Any]:
    """Запись mcp_servers типа sdk: сервер в процессе панели с именем сервиса.

    Имя сервера равно service_id, поэтому инструменты остаются mcp__<service_id>__*.
    """
    if not supported():
        raise RuntimeError("прокси подключений требует mcp 2.x")
    from mcp.server.lowlevel import Server
    from mcp.shared.exceptions import MCPError
    from mcp.types import INTERNAL_ERROR, CallToolResult, ListToolsResult, TextContent

    upstream = _Upstream(service_id, config)

    async def on_list_tools(ctx: Any, params: Any) -> Any:
        try:
            tools = await upstream.list_tools()
        except Exception as exc:  # noqa: BLE001 — наружу только безопасный текст
            _log_failure(service_id, "list_tools", exc)
            raise MCPError(INTERNAL_ERROR, _safe_message(service_id, exc)) from None
        return ListToolsResult(tools=tools)

    async def on_call_tool(ctx: Any, params: Any) -> Any:
        try:
            return await upstream.call_tool(params.name, params.arguments or {})
        except Exception as exc:  # noqa: BLE001 — наружу только безопасный текст
            _log_failure(service_id, "call_tool", exc)
            text = _safe_message(service_id, exc)
            return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)

    server = Server(
        service_id,
        version=SERVER_VERSION,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )
    return {"type": "sdk", "name": service_id, "instance": server}
