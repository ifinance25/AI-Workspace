"""Unit tests for multi-provider API key rows and LLM prefs."""
from __future__ import annotations

from cryptography.fernet import Fernet

from src.apikeys.crypto import ApiKeyCrypto
from src.apikeys.policy import NeedsApiKeyError
from src.apikeys.providers import launch_for_user
from src.apikeys.store import ApiKeyStore

CLAUDE_KEY = "sk-ant-api03-EXAMPLEplaintext1234"
OPENAI_KEY = "sk-openai-EXAMPLEKEY0001"
KIMI_KEY = "sk-kimi-EXAMPLEKEY00001"


def _store(tmp_path) -> ApiKeyStore:
    return ApiKeyStore(tmp_path / "apikeys.db", ApiKeyCrypto(Fernet.generate_key().decode()))


def test_keys_isolated_by_provider(tmp_path):
    store = _store(tmp_path)
    store.set_key(1, CLAUDE_KEY, provider="claude")
    store.set_key(1, OPENAI_KEY, provider="openai")
    assert store.get_key(1) == CLAUDE_KEY
    assert store.get_key(1, "openai") == OPENAI_KEY
    assert store.get_key(1, "kimi") is None


def test_delete_one_provider_keeps_the_other(tmp_path):
    store = _store(tmp_path)
    store.set_key(1, CLAUDE_KEY, provider="claude")
    store.set_key(1, OPENAI_KEY, provider="openai")
    assert store.delete_key(1, "openai") is True
    assert store.get_key(1, "claude") == CLAUDE_KEY
    assert store.get_key(1, "openai") is None


def test_legacy_db_migrates_to_claude_provider(tmp_path):
    """База без колонки provider читается как claude."""
    import sqlite3

    db = tmp_path / "old.db"
    crypto = ApiKeyCrypto(Fernet.generate_key().decode())
    enc = crypto.encrypt(CLAUDE_KEY)
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE user_api_keys (
            user_id INTEGER PRIMARY KEY,
            key_encrypted TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            last4 TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO user_api_keys (user_id, key_encrypted, status, last4, created_at, updated_at) "
        "VALUES (3, ?, 'active', ?, '2026-01-01', '2026-01-01')",
        (enc, CLAUDE_KEY[-4:]),
    )
    conn.commit()
    conn.close()

    store = ApiKeyStore(db, crypto)
    assert store.get_key(3, "claude") == CLAUDE_KEY
    assert store.get_meta(3)["last4"] == CLAUDE_KEY[-4:]


def test_prefs_roundtrip(tmp_path):
    store = _store(tmp_path)
    prefs = store.set_prefs(
        1, active_provider="kimi", model="kimi-k2.5", provider_for_model="kimi"
    )
    assert prefs["active_provider"] == "kimi"
    assert prefs["models"]["kimi"] == "kimi-k2.5"
    loaded = store.get_prefs(1)
    assert loaded == prefs


def test_launch_kimi_injects_base_url(tmp_path):
    store = _store(tmp_path)
    store.set_key(1, KIMI_KEY, provider="kimi")
    store.set_prefs(1, active_provider="kimi", model="kimi-k2.5", provider_for_model="kimi")
    launch = launch_for_user(
        store, 1, is_privileged=False, require_user_key=True
    )
    assert launch.provider == "kimi"
    assert launch.api_key == KIMI_KEY
    assert launch.extra_env["ANTHROPIC_BASE_URL"] == "https://api.moonshot.ai/anthropic"


def test_launch_openai_without_proxy_refuses(tmp_path):
    store = _store(tmp_path)
    store.set_key(1, OPENAI_KEY, provider="openai")
    store.set_prefs(1, active_provider="openai")
    try:
        launch_for_user(store, 1, is_privileged=True, require_user_key=False)
        raise AssertionError("expected NeedsApiKeyError")
    except NeedsApiKeyError as exc:
        assert "прокси" in str(exc).lower() or "Anthropic" in str(exc)


def test_launch_legacy_store_without_get_prefs():
    class _Legacy:
        def get_key(self, user_id: int) -> str | None:
            return CLAUDE_KEY

    launch = launch_for_user(
        _Legacy(), 9, is_privileged=False, require_user_key=True
    )
    assert launch.api_key == CLAUDE_KEY
    assert launch.extra_env == {}
