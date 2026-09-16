"""Validate SSH private keys and compute an OpenSSH-style fingerprint.

The private key itself never leaves this module as a return value of a
public helper except ``fingerprint_private_key`` (hash only). Callers
store the original PEM/OpenSSH text after a successful parse.
"""
from __future__ import annotations

import base64
import hashlib
import re
from typing import Any

from cryptography.hazmat.primitives import serialization

_BEGIN_RE = re.compile(
    r"-----BEGIN (?:OPENSSH |RSA |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"
)
MAX_KEY_CHARS = 32_768


class InvalidSshKeyError(ValueError):
    """Raised when the pasted key cannot be loaded."""


def _password_bytes(passphrase: str | None) -> bytes | None:
    if passphrase is None:
        return None
    text = passphrase.strip()
    return text.encode() if text else None


def load_private_key(text: str, passphrase: str | None = None) -> Any:
    """Parse a PEM or OpenSSH private key. Raises ``InvalidSshKeyError``."""
    blob = (text or "").strip().replace("\r\n", "\n")
    if not blob:
        raise InvalidSshKeyError("Ключ пустой")
    if len(blob) > MAX_KEY_CHARS:
        raise InvalidSshKeyError("Ключ слишком большой")
    if _BEGIN_RE.search(blob) is None:
        raise InvalidSshKeyError(
            "Это не SSH-ключ: вставьте текст, который начинается с "
            "-----BEGIN OPENSSH PRIVATE KEY----- или -----BEGIN PRIVATE KEY-----"
        )
    password = _password_bytes(passphrase)
    raw = blob.encode()
    try:
        return serialization.load_ssh_private_key(raw, password=password)
    except (ValueError, TypeError) as first_exc:
        try:
            return serialization.load_pem_private_key(raw, password=password)
        except (ValueError, TypeError) as exc:
            msg = f"{first_exc} {exc}".lower()
            if password is None and (
                "encrypt" in msg or "password" in msg or "passphrase" in msg
            ):
                raise InvalidSshKeyError("Для этого ключа нужна парольная фраза") from exc
            if password is not None and (
                "password" in msg
                or "passphrase" in msg
                or "decrypt" in msg
                or "bad" in msg
            ):
                raise InvalidSshKeyError("Неверная парольная фраза для ключа") from exc
            raise InvalidSshKeyError("Не удалось прочитать SSH-ключ") from exc


def fingerprint_private_key(text: str, passphrase: str | None = None) -> str:
    """OpenSSH SHA256 fingerprint of the public half (``SHA256:…``)."""
    key = load_private_key(text, passphrase)
    openssh = key.public_key().public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH,
    )
    parts = openssh.split()
    if len(parts) < 2:
        raise InvalidSshKeyError("Не удалось посчитать отпечаток ключа")
    raw = base64.b64decode(parts[1])
    digest = hashlib.sha256(raw).digest()
    return "SHA256:" + base64.b64encode(digest).rstrip(b"=").decode("ascii")
