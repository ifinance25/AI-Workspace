"""SQLite store for per-user LLM API keys (encrypted at rest).

Follows the raw-sqlite3 + lock + WAL pattern used by ``SessionManager`` and
``ConnectionsStore``: a single long-lived connection with WAL journaling so it
can coexist with the sessions/connections DBs. Keys are encrypted via
:class:`ApiKeyCrypto` before they ever touch disk; only a ``last4`` fragment is
stored in the clear so the UI can show which key is configured without
decryption.

Rows are keyed by ``(user_id, provider)``. A database created before providers
existed is migrated in place: the old single row becomes ``provider='claude'``.
Legacy callers that omit ``provider`` still read/write the Claude key.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from src.apikeys.crypto import ApiKeyCrypto

_DEFAULT_PROVIDER = "claude"

_KEYS_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_api_keys (
    user_id INTEGER NOT NULL,
    provider TEXT NOT NULL DEFAULT 'claude',
    key_encrypted TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    last4 TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    auth_kind TEXT NOT NULL DEFAULT 'api_key',
    extra TEXT,
    PRIMARY KEY (user_id, provider)
);
"""

_PREFS_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_llm_prefs (
    user_id INTEGER PRIMARY KEY,
    active_provider TEXT NOT NULL DEFAULT 'claude',
    models_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
"""


class ApiKeyStore:
    def __init__(self, db_path: str | Path, crypto: ApiKeyCrypto):
        self._path = Path(db_path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._crypto = crypto
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._initialize_db()

    def _connection(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(self._path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        self._conn = conn
        return conn

    def _initialize_db(self) -> None:
        with self._lock:
            conn = self._connection()
            self._migrate_keys_table(conn)
            conn.executescript(_PREFS_SCHEMA)
            conn.commit()

    def _migrate_keys_table(self, conn: sqlite3.Connection) -> None:
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_api_keys'"
        ).fetchone()
        if exists is None:
            conn.executescript(_KEYS_SCHEMA)
            return
        cols = {row[1] for row in conn.execute("PRAGMA table_info(user_api_keys)")}
        if "provider" in cols and "auth_kind" in cols and "extra" in cols:
            return
        conn.executescript(
            """
            CREATE TABLE user_api_keys_new (
                user_id INTEGER NOT NULL,
                provider TEXT NOT NULL DEFAULT 'claude',
                key_encrypted TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                last4 TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                auth_kind TEXT NOT NULL DEFAULT 'api_key',
                extra TEXT,
                PRIMARY KEY (user_id, provider)
            );
            INSERT INTO user_api_keys_new (
                user_id, provider, key_encrypted, status, last4,
                created_at, updated_at, auth_kind, extra
            )
            SELECT
                user_id,
                'claude',
                key_encrypted,
                status,
                last4,
                created_at,
                updated_at,
                'api_key',
                NULL
            FROM user_api_keys;
            DROP TABLE user_api_keys;
            ALTER TABLE user_api_keys_new RENAME TO user_api_keys;
            """
        )

    def set_key(
        self,
        user_id: int,
        key: str,
        *,
        status: str = "active",
        provider: str = _DEFAULT_PROVIDER,
        auth_kind: str = "api_key",
        extra: dict | None = None,
    ) -> None:
        """Encrypt and persist ``key`` for ``user_id`` (insert or update)."""
        now = datetime.now().isoformat()
        enc = self._crypto.encrypt(key)
        last4 = key[-4:]
        extra_json = json.dumps(extra) if extra is not None else None
        with self._lock:
            self._connection().execute(
                """
                INSERT INTO user_api_keys
                    (user_id, provider, key_encrypted, status, last4,
                     created_at, updated_at, auth_kind, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, provider) DO UPDATE SET
                    key_encrypted = excluded.key_encrypted,
                    status = excluded.status,
                    last4 = excluded.last4,
                    updated_at = excluded.updated_at,
                    auth_kind = excluded.auth_kind,
                    extra = COALESCE(excluded.extra, user_api_keys.extra)
                """,
                (
                    user_id,
                    provider,
                    enc,
                    status,
                    last4,
                    now,
                    now,
                    auth_kind,
                    extra_json,
                ),
            )
            self._connection().commit()

    def get_key(self, user_id: int, provider: str = _DEFAULT_PROVIDER) -> str | None:
        """Return the decrypted key, or ``None`` if absent/undecryptable."""
        with self._lock:
            row = self._connection().execute(
                "SELECT key_encrypted FROM user_api_keys "
                "WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            ).fetchone()
        if row is None:
            return None
        return self._crypto.decrypt(row["key_encrypted"])

    def has_key(self, user_id: int, provider: str | None = None) -> bool:
        """True if a key row exists (no decryption performed)."""
        with self._lock:
            if provider is None:
                row = self._connection().execute(
                    "SELECT 1 FROM user_api_keys WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
            else:
                row = self._connection().execute(
                    "SELECT 1 FROM user_api_keys WHERE user_id = ? AND provider = ?",
                    (user_id, provider),
                ).fetchone()
        return row is not None

    def get_meta(self, user_id: int, provider: str = _DEFAULT_PROVIDER) -> dict | None:
        """Return non-secret metadata (never the key itself).

        A trial decrypt detects a stored-but-undecryptable key (e.g. after a
        ``CONNECTIONS_SECRET_KEY`` rotation): in that case the reported status is
        overridden to ``needs_reentry`` so the UI can prompt for a fresh key. The
        decrypted value is only tested for ``None`` — it is never returned nor
        logged. ``last4`` and timestamps are preserved regardless.
        """
        row = self._row(user_id, provider)
        if row is None:
            return None
        status = row["status"]
        if self._crypto.decrypt(row["key_encrypted"]) is None:
            status = "needs_reentry"
        return {
            "status": status,
            "last4": row["last4"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_provider_meta(self, user_id: int, provider: str) -> dict | None:
        """Metadata plus ``auth_kind`` / ``extra`` for one provider."""
        row = self._row(user_id, provider)
        if row is None:
            return None
        meta = self.get_meta(user_id, provider)
        if meta is None:
            return None
        extra = {}
        raw = row["extra"]
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    extra = parsed
            except json.JSONDecodeError:
                extra = {}
        return {
            **meta,
            "auth_kind": row["auth_kind"] or "api_key",
            "extra": extra,
        }

    def list_meta(self, user_id: int) -> dict[str, dict]:
        """Map provider id → metadata (no secrets)."""
        with self._lock:
            rows = self._connection().execute(
                "SELECT provider FROM user_api_keys WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        out: dict[str, dict] = {}
        for row in rows:
            pid = row["provider"]
            meta = self.get_provider_meta(user_id, pid)
            if meta is not None:
                out[pid] = meta
        return out

    def set_provider_extra(self, user_id: int, provider: str, extra: dict) -> None:
        """Update extra JSON (base_url etc.) without touching the secret."""
        extra_json = json.dumps(extra)
        now = datetime.now().isoformat()
        with self._lock:
            self._connection().execute(
                """
                UPDATE user_api_keys
                SET extra = ?, updated_at = ?
                WHERE user_id = ? AND provider = ?
                """,
                (extra_json, now, user_id, provider),
            )
            self._connection().commit()

    def delete_key(self, user_id: int, provider: str = _DEFAULT_PROVIDER) -> bool:
        """Delete the key; return True if a row was removed."""
        with self._lock:
            cur = self._connection().execute(
                "DELETE FROM user_api_keys WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            )
            self._connection().commit()
        return (cur.rowcount or 0) > 0

    def get_prefs(self, user_id: int) -> dict:
        with self._lock:
            row = self._connection().execute(
                "SELECT active_provider, models_json FROM user_llm_prefs WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return {"active_provider": _DEFAULT_PROVIDER, "models": {}}
        models: dict = {}
        try:
            parsed = json.loads(row["models_json"] or "{}")
            if isinstance(parsed, dict):
                models = parsed
        except json.JSONDecodeError:
            models = {}
        return {
            "active_provider": row["active_provider"] or _DEFAULT_PROVIDER,
            "models": models,
        }

    def set_prefs(
        self,
        user_id: int,
        *,
        active_provider: str | None = None,
        model: str | None = None,
        provider_for_model: str | None = None,
    ) -> dict:
        current = self.get_prefs(user_id)
        if active_provider:
            current["active_provider"] = active_provider
        if model and provider_for_model:
            models = dict(current.get("models") or {})
            models[provider_for_model] = model
            current["models"] = models
        now = datetime.now().isoformat()
        with self._lock:
            self._connection().execute(
                """
                INSERT INTO user_llm_prefs (user_id, active_provider, models_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    active_provider = excluded.active_provider,
                    models_json = excluded.models_json,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    current["active_provider"],
                    json.dumps(current["models"]),
                    now,
                ),
            )
            self._connection().commit()
        return current

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _row(self, user_id: int, provider: str) -> sqlite3.Row | None:
        with self._lock:
            return self._connection().execute(
                "SELECT key_encrypted, status, last4, created_at, updated_at, "
                "auth_kind, extra FROM user_api_keys "
                "WHERE user_id = ? AND provider = ?",
                (user_id, provider),
            ).fetchone()
