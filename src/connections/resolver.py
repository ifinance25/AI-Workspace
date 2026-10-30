"""Assemble a user's connected services into an mcp_servers dict.

Called by bot/web handlers before dispatching to the Claude bridge. Secrets are
decrypted here and live only in the returned dict (in memory). Unknown or
undecryptable services are skipped so one bad row never breaks the chat.
"""
from __future__ import annotations

from typing import Any

import structlog

from src.connections import catalog, kb_tools
from src.connections.store import ConnectionsStore

logger = structlog.get_logger()

# Общий MCP-сервер базы знаний ФАКТ (пилот): один на всех пользователей и проекты.
SHARED_KB_SERVER_NAME = kb_tools.SERVER_NAME


def build_mcp_servers(user_id: int, store: ConnectionsStore) -> dict[str, dict[str, Any]]:
    servers: dict[str, dict[str, Any]] = {}
    for service_id in store.list_service_ids(user_id):
        svc = catalog.get_service(service_id)
        if svc is None:
            continue
        secret = store.get_secret(user_id, service_id)
        if not secret:
            continue
        try:
            servers[service_id] = svc.build_mcp_server(secret)
        except Exception as exc:  # noqa: BLE001 — never let one service break dispatch
            logger.warning("mcp_build_failed", user_id=user_id, service_id=service_id, error=str(exc))
    return servers


def _kb_setting(settings: Any, getter_name: str) -> str:
    """Значение настройки базы знаний или "".

    Relay принимает settings как Any, а старая обвязка и тесты передают урезанные
    объекты: геттера может не быть, и это равно выключенному серверу.
    """
    getter = getattr(settings, getter_name, None)
    value = getter() if callable(getter) else ""
    return value.strip() if isinstance(value, str) else ""


def _uses_sdk_transport(settings: Any) -> bool:
    """Запись sdk работает только на пути SDK: tmux не принимает mcp_servers."""
    claude = getattr(settings, "claude", None)
    return getattr(claude, "transport", "sdk") == "sdk"


def build_shared_mcp_servers(settings: Any, user_id: int | None = None) -> dict[str, Any]:
    """Запись общего сервера для сессии, или {}, если пилот не подключить.

    Сервер работает в процессе панели: в аргументы claude уходит только имя и тип
    записи, а адрес и ключ остаются здесь. Пустой результат также выключает лупу
    (kb_search_enabled в src/bot/core.py и scripts/run_web.py).
    """
    url = _kb_setting(settings, "get_kb_mcp_url")
    key = _kb_setting(settings, "get_kb_mcp_key")
    if not url or not key or not _uses_sdk_transport(settings):
        return {}
    if not kb_tools.url_allowed(url):
        logger.warning("kb_url_rejected", reason="нужен https или http на петлевом адресе")
        return {}
    try:
        server = kb_tools.build_kb_server(url, key, user_id=user_id)
    except Exception as exc:  # noqa: BLE001 — без SDK или при сбое сборки чат работает без базы
        logger.warning("kb_server_build_failed", error_class=type(exc).__name__)
        return {}
    return {SHARED_KB_SERVER_NAME: server}


def dispatch_mcp_servers(
    user_id: int,
    store: ConnectionsStore | None,
    settings: Any,
    include_shared: bool = True,
) -> dict[str, Any] | None:
    """MCP-серверы сессии.

    include_shared=True (лупа включена): только общий сервер базы знаний. Модель в
    таком запуске читает внешний текст задач, поэтому личные подключения в него не
    идут, а мост оставляет ей одни инструменты базы. Сервер не собрался: None.

    include_shared=False: только личные подключения. Нет серверов: None.
    Результат содержит секреты: не логировать.
    """
    if include_shared:
        return build_shared_mcp_servers(settings, user_id=user_id) or None
    servers = build_mcp_servers(user_id, store) if store is not None else {}
    return servers or None
