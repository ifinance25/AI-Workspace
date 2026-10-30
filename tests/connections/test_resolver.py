import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import structlog
from cryptography.fernet import Fernet
from src.config.settings import Settings
from src.connections import kb_tools
from src.connections.crypto import SecretBox
from src.connections.store import ConnectionsStore
from src.connections.resolver import (
    SHARED_KB_SERVER_NAME,
    build_mcp_servers,
    build_shared_mcp_servers,
    dispatch_mcp_servers,
)

KB_URL = "https://kb.example.test/mcp"
KB_KEY = "test-key-123"


def _store(tmp_path):
    return ConnectionsStore(tmp_path / "c.db", SecretBox(Fernet.generate_key().decode()))


def test_build_returns_server_with_injected_secret(tmp_path):
    store = _store(tmp_path)
    store.connect(user_id=1, service_id="notion", secret="tok-x")
    servers = build_mcp_servers(1, store)
    assert "notion" in servers
    assert servers["notion"]["env"]["NOTION_TOKEN"] == "tok-x"


def test_empty_for_user_without_connections(tmp_path):
    assert build_mcp_servers(999, _store(tmp_path)) == {}


def test_unknown_service_id_is_skipped(tmp_path):
    store = _store(tmp_path)
    store.connect(user_id=1, service_id="ghost", secret="x")  # not in catalog
    assert build_mcp_servers(1, store) == {}


def test_isolation_user_b_not_leaked(tmp_path):
    store = _store(tmp_path)
    store.connect(user_id=1, service_id="notion", secret="a")
    store.connect(user_id=2, service_id="github", secret="b")
    assert set(build_mcp_servers(1, store)) == {"notion"}


# --- Общий сервер базы знаний ФАКТ (пилот) ------------------------------------


def _kb_settings(url: str = KB_URL, key: str = KB_KEY, *, transport: str = "sdk") -> SimpleNamespace:
    return SimpleNamespace(
        get_kb_mcp_url=lambda: url,
        get_kb_mcp_key=lambda: key,
        claude=SimpleNamespace(transport=transport),
    )


def _assert_sdk_record(server: dict) -> None:
    assert server["type"] == "sdk"
    assert server["name"] == SHARED_KB_SERVER_NAME
    assert server["instance"] is not None


def test_settings_read_kb_env_aliases(monkeypatch):
    monkeypatch.setenv("KB_MCP_URL", KB_URL)
    monkeypatch.setenv("KB_MCP_KEY", KB_KEY)
    settings = Settings(_env_file=None)
    assert settings.get_kb_mcp_url() == KB_URL
    assert settings.get_kb_mcp_key() == KB_KEY


def test_settings_kb_getters_default_to_empty(monkeypatch):
    monkeypatch.delenv("KB_MCP_URL", raising=False)
    monkeypatch.delenv("KB_MCP_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.get_kb_mcp_url() == ""
    assert settings.get_kb_mcp_key() == ""


def test_server_name_is_fakt_kb():
    assert SHARED_KB_SERVER_NAME == "fakt_kb"


def test_shared_server_shape():
    servers = build_shared_mcp_servers(_kb_settings())
    assert set(servers) == {"fakt_kb"}
    _assert_sdk_record(servers["fakt_kb"])


def test_shared_server_needs_no_web_settings():
    """Настройка веба и порт больше не нужны: сервер живёт в процессе панели."""
    settings = SimpleNamespace(get_kb_mcp_url=lambda: KB_URL, get_kb_mcp_key=lambda: KB_KEY)
    assert set(build_shared_mcp_servers(settings)) == {"fakt_kb"}


async def test_shared_server_binds_user_id_for_the_log(monkeypatch):
    seen: dict = {}

    def _spy(url, key, *, user_id=None):
        seen.update(url=url, key=key, user_id=user_id)
        return {"type": "sdk", "name": "fakt_kb", "instance": object()}

    monkeypatch.setattr(kb_tools, "build_kb_server", _spy)
    build_shared_mcp_servers(_kb_settings(), user_id=42)
    assert seen == {"url": KB_URL, "key": KB_KEY, "user_id": 42}


def test_dispatch_passes_user_id(monkeypatch):
    seen: list = []

    def _spy(settings, *, user_id=None):
        seen.append(user_id)
        return {}

    monkeypatch.setattr("src.connections.resolver.build_shared_mcp_servers", _spy)
    dispatch_mcp_servers(42, None, _kb_settings())
    assert seen == [42]


@pytest.mark.parametrize("transport", ["tmux", "cli"])
def test_shared_server_only_on_sdk_transport(transport):
    """На tmux mcp_servers не доходят до claude, а запись sdk не сериализуется."""
    assert build_shared_mcp_servers(_kb_settings(transport=transport)) == {}
    assert dispatch_mcp_servers(1, None, _kb_settings(transport=transport)) is None


def test_shared_server_failed_build_disables_pilot_without_values(monkeypatch):
    def _boom(url, key, *, user_id=None):
        raise RuntimeError(f"сломалось на {url} {key}")

    monkeypatch.setattr(kb_tools, "build_kb_server", _boom)
    with structlog.testing.capture_logs() as logs:
        assert build_shared_mcp_servers(_kb_settings()) == {}
    assert any(entry["event"] == "kb_server_build_failed" for entry in logs)
    assert KB_KEY not in repr(logs)
    assert KB_URL not in repr(logs)


@pytest.mark.parametrize(
    "url",
    [
        "http://kb.example.test/mcp",
        "kb.example.test/mcp",
        "http://127.0.0.1.evil.invalid/mcp",
        "https://user:pass@kb.example.test/mcp",
    ],
)
def test_shared_server_rejects_unsafe_url_without_value_in_log(url):
    with structlog.testing.capture_logs() as logs:
        assert build_shared_mcp_servers(_kb_settings(url=url)) == {}
    assert any(entry["event"] == "kb_url_rejected" for entry in logs)
    assert url not in repr(logs)
    assert "kb.example.test" not in repr(logs)


def test_shared_server_accepts_http_on_loopback():
    assert build_shared_mcp_servers(_kb_settings(url="http://127.0.0.1:9090/mcp"))


@pytest.mark.parametrize(
    "settings",
    [
        None,
        _kb_settings(url=""),
        _kb_settings(key=""),
        _kb_settings(url="", key=""),
        _kb_settings(url="   "),
        _kb_settings(key="   "),
    ],
    ids=["no-settings", "no-url", "no-key", "both-empty", "blank-url", "blank-key"],
)
def test_shared_server_disabled_without_config(settings):
    assert build_shared_mcp_servers(settings) == {}
    assert dispatch_mcp_servers(1, None, settings) is None


@pytest.mark.parametrize(
    "settings",
    [SimpleNamespace(require_user_key=True), MagicMock()],
    ids=["settings-without-getters", "mock-settings"],
)
def test_shared_server_ignores_foreign_settings_objects(settings):
    """В тестах и старой обвязке relay получает урезанный settings: это не повод
    падать или отдавать в SDK несериализуемый Mock вместо адреса."""
    assert build_shared_mcp_servers(settings) == {}


def test_shared_server_record_for_cli_has_neither_url_nor_key():
    """Ровно это SDK кладёт в --mcp-config: запись без instance."""
    entry = build_shared_mcp_servers(_kb_settings())["fakt_kb"]
    for_cli = {name: value for name, value in entry.items() if name != "instance"}
    assert for_cli == {"type": "sdk", "name": "fakt_kb"}


def test_dispatch_result_repr_has_neither_url_nor_key(tmp_path):
    store = _store(tmp_path)
    store.connect(user_id=1, service_id="notion", secret="tok-x")
    dumped = repr(dispatch_mcp_servers(1, store, _kb_settings()))
    assert KB_URL not in dumped
    assert KB_KEY not in dumped


def test_dispatch_user_without_connections_gets_shared_server(tmp_path):
    servers = dispatch_mcp_servers(999, _store(tmp_path), _kb_settings())
    assert set(servers) == {"fakt_kb"}
    _assert_sdk_record(servers["fakt_kb"])


def test_dispatch_without_store_gets_shared_server():
    servers = dispatch_mcp_servers(1, None, _kb_settings())
    assert set(servers) == {"fakt_kb"}
    _assert_sdk_record(servers["fakt_kb"])


def test_dispatch_empty_store_and_no_kb_is_none(tmp_path):
    assert dispatch_mcp_servers(1, _store(tmp_path), None) is None


def test_dispatch_store_none_and_settings_none_is_none():
    assert dispatch_mcp_servers(1, None, None) is None


def test_dispatch_keeps_personal_connections_without_kb(tmp_path):
    store = _store(tmp_path)
    store.connect(user_id=1, service_id="notion", secret="tok-x")
    servers = dispatch_mcp_servers(1, store, None, include_shared=False)
    assert set(servers) == {"notion"}


def test_dispatch_with_kb_drops_personal_connections(tmp_path):
    """Лупа включена: в запуск идёт только база, личные подключения не идут."""
    store = _store(tmp_path)
    store.connect(user_id=1, service_id="notion", secret="tok-x")
    servers = dispatch_mcp_servers(1, store, _kb_settings())
    assert set(servers) == {"fakt_kb"}
    _assert_sdk_record(servers["fakt_kb"])
    assert "tok-x" not in repr(servers)


def test_dispatch_with_kb_unavailable_gives_nothing(tmp_path):
    store = _store(tmp_path)
    store.connect(user_id=1, service_id="notion", secret="tok-x")
    assert dispatch_mcp_servers(1, store, _kb_settings(key="")) is None


def test_dispatch_personal_entry_cannot_replace_shared(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.connections.resolver.build_mcp_servers",
        lambda user_id, store: {"fakt_kb": {"type": "http", "url": "https://evil.example.test"}},
    )
    servers = dispatch_mcp_servers(1, _store(tmp_path), _kb_settings())
    _assert_sdk_record(servers["fakt_kb"])


def test_dispatch_isolation_shared_server_does_not_leak_personal(tmp_path):
    store = _store(tmp_path)
    store.connect(user_id=1, service_id="notion", secret="a")
    assert set(dispatch_mcp_servers(2, store, _kb_settings())) == {"fakt_kb"}


def test_dispatch_does_not_log_key(tmp_path, caplog, capsys):
    store = _store(tmp_path)
    store.connect(user_id=1, service_id="notion", secret="tok-x")
    store.connect(user_id=1, service_id="ghost", secret="x")  # ветка пропуска
    with caplog.at_level(logging.DEBUG), structlog.testing.capture_logs() as logs:
        servers = dispatch_mcp_servers(1, store, _kb_settings(), include_shared=False)
        dispatch_mcp_servers(1, None, _kb_settings())
    assert servers  # сборка реально прошла
    assert KB_KEY not in repr(logs)
    assert KB_KEY not in caplog.text
    captured = capsys.readouterr()
    assert KB_KEY not in captured.out + captured.err


def test_dispatch_does_not_log_key_when_personal_build_fails(tmp_path, monkeypatch):
    """Единственная ветка с логом в сборке: падение личного сервиса."""
    store = _store(tmp_path)
    store.connect(user_id=1, service_id="notion", secret="tok-x")

    def _boom(secret):
        raise ValueError("boom")

    fake = SimpleNamespace(build_mcp_server=_boom)
    monkeypatch.setattr("src.connections.resolver.catalog.get_service", lambda _id: fake)
    with structlog.testing.capture_logs() as logs:
        servers = dispatch_mcp_servers(1, store, _kb_settings(), include_shared=False)
    assert servers is None
    assert any(entry["event"] == "mcp_build_failed" for entry in logs)
    assert KB_KEY not in repr(logs)
