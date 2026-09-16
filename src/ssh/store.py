"""SQLite store for per-user SSH profiles (encrypted private key)."""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import structlog

from src.connections.crypto import SecretBox, SecretDecryptError

logger = structlog.get_logger()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_ssh_profiles (
    user_id INTEGER PRIMARY KEY,
    blob_encrypted TEXT NOT NULL,
    fingerprint TEXT,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class SshProfile:
    host: str
    port: int
    username: str
    private_key: str
    passphrase: str | None
    fingerprint: str


class SshStore:
    def __init__(self, db_path: str | Path, secret_box: SecretBox):
        self._path = Path(db_path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._box = secret_box
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        self._init_schema()

    def _connection(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(self._path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        self._conn = conn
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            self._connection().executescript(_SCHEMA)
            self._connection().commit()

    def get(self, user_id: int) -> SshProfile | None:
        with self._lock:
            row = self._connection().execute(
                "SELECT blob_encrypted, fingerprint FROM user_ssh_profiles "
                "WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            raw = self._box.decrypt(row["blob_encrypted"])
            data = json.loads(raw)
        except (SecretDecryptError, json.JSONDecodeError, TypeError):
            logger.warning("ssh_profile_undecryptable", user_id=user_id)
            return None
        passphrase = data.get("passphrase") or None
        if isinstance(passphrase, str) and not passphrase.strip():
            passphrase = None
        return SshProfile(
            host=str(data.get("host") or ""),
            port=int(data.get("port") or 22),
            username=str(data.get("username") or ""),
            private_key=str(data.get("private_key") or ""),
            passphrase=passphrase,
            fingerprint=str(row["fingerprint"] or data.get("fingerprint") or ""),
        )

    def save(self, user_id: int, profile: SshProfile) -> None:
        payload = json.dumps(
            {
                "host": profile.host,
                "port": profile.port,
                "username": profile.username,
                "private_key": profile.private_key,
                "passphrase": profile.passphrase or "",
            },
            ensure_ascii=False,
        )
        enc = self._box.encrypt(payload)
        with self._lock:
            self._connection().execute(
                """
                INSERT INTO user_ssh_profiles
                    (user_id, blob_encrypted, fingerprint, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    blob_encrypted = excluded.blob_encrypted,
                    fingerprint = excluded.fingerprint,
                    updated_at = excluded.updated_at
                """,
                (user_id, enc, profile.fingerprint, _now()),
            )
            self._connection().commit()
        logger.info(
            "ssh_profile_saved",
            user_id=user_id,
            host=profile.host,
            username=profile.username,
            fingerprint=profile.fingerprint,
        )

    def delete(self, user_id: int) -> bool:
        with self._lock:
            cur = self._connection().execute(
                "DELETE FROM user_ssh_profiles WHERE user_id = ?",
                (user_id,),
            )
            self._connection().commit()
        return (cur.rowcount or 0) > 0

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
