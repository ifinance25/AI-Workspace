"""Токен личного подключения не уходит в процесс claude.

Раньше SDK клал запись GitHub (заголовок Authorization) и Notion (NOTION_TOKEN) в аргумент
--mcp-config, и токен видел любой процесс машины через ps. Теперь запись типа sdk: в
аргументах только имя и тип. Запасной CLI-путь запись sdk не берёт и идёт без подключений.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from src.claude.bridge import ClaudeBridge
from src.connections.crypto import SecretBox
from src.connections.resolver import dispatch_mcp_servers
from src.connections.store import ConnectionsStore
from tests.connections.test_bridge_shared_kb import (
    _argv,
    _flag_values,
    _record_cli_run,
    _run_cli,
    _sdk_options,
)
from tests.spawn_audit import spawn_audit  # noqa: F401

pytestmark = pytest.mark.usefixtures("spawn_audit")

TOKENS = {"github": "ghp_FAKE_TEST_TOKEN_123", "notion": "ntn_FAKE_TEST_TOKEN_456"}
SDK_SETTINGS = SimpleNamespace(claude=SimpleNamespace(transport="sdk"))


@pytest.fixture
def servers(tmp_path) -> dict:
    store = ConnectionsStore(tmp_path / "c.db", SecretBox(Fernet.generate_key().decode()))
    for service_id, token in TOKENS.items():
        store.connect(user_id=1, service_id=service_id, secret=token)
    result = dispatch_mcp_servers(1, store, SDK_SETTINGS, include_shared=False)
    assert set(result) == set(TOKENS)
    return result


def _assert_no_token(blob: str) -> None:
    for token in TOKENS.values():
        assert token not in blob


@pytest.mark.parametrize("service_id", sorted(TOKENS))
@pytest.mark.parametrize(
    "bridge_kwargs, options_kwargs",
    [
        ({}, {}),
        ({"permission_mode": "default"}, {}),
        ({}, {"readonly": True}),
        ({}, {"confine_root": "/tmp/project"}),
    ],
    ids=["bypass", "default-mode", "readonly", "confined"],
)
def test_sdk_argv_has_no_token(servers, service_id, bridge_kwargs, options_kwargs):
    one = {service_id: servers[service_id]}
    options = _sdk_options(ClaudeBridge(**bridge_kwargs), one, **options_kwargs)
    argv = _argv(options)
    for part in argv:
        _assert_no_token(part)
    config = json.loads(_flag_values(argv, "--mcp-config")[0])
    assert config == {"mcpServers": {service_id: {"type": "sdk", "name": service_id}}}


def test_sdk_argv_and_env_have_no_token_with_both(servers):
    options = _sdk_options(ClaudeBridge(), servers)
    _assert_no_token(" ".join(_argv(options)))
    _assert_no_token(json.dumps(dict(options.env or {})))
    config = json.loads(_flag_values(_argv(options), "--mcp-config")[0])
    assert set(config["mcpServers"]) == set(TOKENS)


def test_cli_fallback_writes_no_temp_config(servers):
    """Запасной путь: записи sdk не сериализуются, файла с токеном нет."""
    assert ClaudeBridge()._write_temp_mcp_config(servers) is None


async def test_cli_fallback_run_has_no_token(monkeypatch, servers):
    bridge = ClaudeBridge()
    captured = _record_cli_run(monkeypatch, bridge)
    await _run_cli(bridge, servers)
    assert captured["config_path"] is None
    assert "--mcp-config" not in captured["args"]
    _assert_no_token(" ".join(captured["args"]))

