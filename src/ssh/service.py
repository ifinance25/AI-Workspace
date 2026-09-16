"""Factory: build the SshStore from Settings (or None if encryption is off)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from src.connections.crypto import SecretBox
from src.ssh.store import SshStore

logger = structlog.get_logger()

_DEFAULT_DB_PATH = "sessions.db"


def _resolve_secret(settings: Any) -> str | None:
    getter = getattr(settings, "get_connections_secret_key", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            value = None
        if value:
            return value
    return getattr(settings, "connections_secret_key", None) or None


def _resolve_db_path(settings: Any) -> str | Path:
    getter = getattr(settings, "get_session_database_path", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            value = None
        if value:
            return value
    return getattr(settings, "db_path", None) or _DEFAULT_DB_PATH


def build_ssh_store(settings: Any) -> SshStore | None:
    """Return an SshStore, or None if CONNECTIONS_SECRET_KEY is unset."""
    key = _resolve_secret(settings)
    if not key:
        logger.info("ssh_disabled_no_key")
        return None
    return SshStore(_resolve_db_path(settings), SecretBox(key))
