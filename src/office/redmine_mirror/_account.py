"""Учётная запись Redmine для всей Платформы. Токен в ответы не входит.

Токен шифруется ключом ``CONNECTIONS_SECRET_KEY`` (как подключения и SSH, У43-07).
Без ключа адрес и проект сохраняются, а токен не принимается: панель не выводит
шифр из подписи cookie и не хранит токен открытым.
"""

from __future__ import annotations

import base64
import hashlib
import os
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken

from src.utils.url_safety import is_loopback_host

_SCHEMA = """
CREATE TABLE IF NOT EXISTS office_redmine_account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    base_url TEXT NOT NULL DEFAULT '',
    redmine_project TEXT NOT NULL DEFAULT '',
    token_encrypted TEXT NOT NULL DEFAULT ''
);
"""


def url_allowed(base_url: str) -> bool:
    """https на любой хост; http только на петлевой адрес (У43-05).

    Ключ идёт заголовком в каждом запросе: по http он виден в сети, а редирект
    на чужой хост увёл бы его туда.
    """
    try:
        parts = urlsplit(base_url.strip())
    except ValueError:
        return False
    host = parts.hostname or ""
    if not host or parts.username is not None or parts.password is not None:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and is_loopback_host(host)


class TokenStorageDisabledError(RuntimeError):
    """Токен прислали, а ключа шифрования на сервере нет."""


def cipher_from_key(key: str | None) -> Fernet | None:
    """Fernet от готового ключа ``CONNECTIONS_SECRET_KEY``; пусто значит выключено."""
    value = (key or "").strip()
    return Fernet(value.encode()) if value else None


def cipher_for(secret: str) -> Fernet:
    """Шифр из произвольной строки.

    Только для тестов: маршруты берут ``cipher_from_key``.
    """
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _ensure(store) -> None:
    with store._lock:
        store._connection().executescript(_SCHEMA)


def _row(store) -> dict:
    _ensure(store)
    with store._lock:
        found = store._connection().execute(
            "SELECT base_url, redmine_project, token_encrypted FROM office_redmine_account WHERE id = 1"
        ).fetchone()
    if found is None:
        return {"base_url": "", "redmine_project": "", "token_encrypted": ""}
    return dict(found)


def _decrypt(cipher: Fernet | None, encrypted: str) -> str:
    if not encrypted or cipher is None:
        return ""
    try:
        return cipher.decrypt(encrypted.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return ""


def account_view(store, cipher: Fernet | None) -> dict:
    row = _row(store)
    token = _decrypt(cipher, row["token_encrypted"])
    return {
        "base_url": row["base_url"],
        "redmine_project": row["redmine_project"],
        "has_token": bool(token),
        "last4": token[-4:] if len(token) >= 4 else "",
    }


def save_account(
    store,
    cipher: Fernet | None,
    *,
    base_url: str,
    redmine_project: str,
    api_key: str | None,
) -> dict:
    if base_url.strip() and not url_allowed(base_url):
        raise ValueError(
            "Адрес Redmine должен начинаться с https:// (http только для 127.0.0.1)"
        )
    current = _row(store)
    if cipher is None:
        if api_key and api_key.strip():
            raise TokenStorageDisabledError(
                "Хранение ключа Redmine выключено: "
                "на сервере не задан CONNECTIONS_SECRET_KEY"
            )
        # Адрес и проект можно менять; старый шифртекст остаётся как есть.
        encrypted = current["token_encrypted"]
    else:
        token = _decrypt(cipher, current["token_encrypted"])
        if api_key:
            token = api_key.strip()
        encrypted = cipher.encrypt(token.encode()).decode() if token else ""
    with store._lock:
        conn = store._connection()
        conn.execute(
            "INSERT INTO office_redmine_account (id, base_url, redmine_project, token_encrypted) "
            "VALUES (1, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "base_url = excluded.base_url, "
            "redmine_project = excluded.redmine_project, "
            "token_encrypted = excluded.token_encrypted",
            (base_url.strip().rstrip("/"), redmine_project.strip(), encrypted),
        )
        conn.commit()
    return account_view(store, cipher)


def resolve_access(store, cipher: Fernet | None, base_url: str, redmine_project: str) -> tuple[str, str, str]:
    """Адрес, проект и токен.

    Сохранённый ключ уходит только на адрес, который записал администратор.
    Адрес из запроса участника этот адрес не подменяет: иначе ключ уйдёт
    на чужой сервер в заголовке ``X-Redmine-API-Key``.
    """
    del base_url
    row = _row(store) if cipher is not None else {"base_url": "", "redmine_project": "", "token_encrypted": ""}
    saved = _decrypt(cipher, row["token_encrypted"]) if cipher is not None else ""
    key = saved or os.environ.get("REDMINE_API_KEY", "")
    return (
        (row["base_url"] or "").rstrip("/"),
        redmine_project or row["redmine_project"] or "",
        key,
    )
