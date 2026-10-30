"""Окружение подпроцесса Claude строится по белому списку: имя вне списка не проходит,
нужные Claude ключи сохраняются, рабочее окружение (PATH) остаётся."""
import dataclasses
import json
import os
import stat
import sys

import pytest

from src.claude.bridge import ClaudeBridge
from tests.spawn_audit import spawn_audit  # noqa: F401

pytestmark = pytest.mark.usefixtures("spawn_audit")


def test_clean_env_scrubs_known_and_future_secrets(monkeypatch) -> None:
    monkeypatch.setenv("WEB_JWT_SECRET", "s")          # известный денилист
    monkeypatch.setenv("SOME_FUTURE_TOKEN", "t")       # будущий секрет (_TOKEN$)
    monkeypatch.setenv("DB_PASSWORD", "p")             # PASSWORD
    monkeypatch.setenv("STRIPE_API_KEY", "k")          # _API_KEY$
    monkeypatch.setenv("MY_BEARER", "b")               # BEARER
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key")     # нужен Claude — сохраняем
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "o")  # нужен Claude — сохраняем

    env = ClaudeBridge._clean_env()

    assert "WEB_JWT_SECRET" not in env
    assert "SOME_FUTURE_TOKEN" not in env
    assert "DB_PASSWORD" not in env
    assert "STRIPE_API_KEY" not in env
    assert "MY_BEARER" not in env
    # Keep-list: авторизация Claude не должна сломаться.
    assert env.get("ANTHROPIC_API_KEY") == "key"
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "o"
    # Рабочее окружение (Bash) сохраняется (PATH не вычищается).
    assert "PATH" in env or "Path" in env


def test_confined_env_strips_anthropic_when_subscription_present(monkeypatch):
    from src.claude.bridge import ClaudeBridge
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-secret")
    monkeypatch.setattr(ClaudeBridge, "_subscription_creds_present", staticmethod(lambda: True))
    env = ClaudeBridge._clean_env(confined=True)
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_confined_env_keeps_anthropic_when_no_subscription(monkeypatch):
    from src.claude.bridge import ClaudeBridge
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setattr(ClaudeBridge, "_subscription_creds_present", staticmethod(lambda: False))
    env = ClaudeBridge._clean_env(confined=True)
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-secret"


def test_nonconfined_env_keeps_anthropic(monkeypatch):
    from src.claude.bridge import ClaudeBridge
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setattr(ClaudeBridge, "_subscription_creds_present", staticmethod(lambda: True))
    env = ClaudeBridge._clean_env(confined=False)
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-secret"


# --- Настоящий запуск: окружение процесса, а не options.env --------------------
#
# SDK собирает окружение как {**os.environ, ..., **options.env}, поэтому удаление
# имени из options.env ничего не меняет: значение возвращается из os.environ.
# Здесь запускается настоящий SubprocessCLITransport, а вместо claude стоит
# заглушка, которая записывает своё настоящее окружение и аргументы.

FAKE_SECRETS = {
    "KB_MCP_KEY": "fake-kb-key-0123456789",
    "KB_MCP_URL": "https://kb.example.invalid/fake-path",
    "WEB_JWT_SECRET": "fake-jwt-secret-0123456789",
    "TELEGRAM_BOT_TOKEN": "12345:fake-telegram-token",
    "CONNECTIONS_SECRET_KEY": "fake-connections-key-0123",
    "ADMIN_PASSWORD": "fake-admin-password-0123",
    "ADMIN_LOGIN": "fake-admin-login-0123",
    "WEB_DEV_BEARER_TOKEN": "fake-dev-bearer-0123",
    "SOME_FUTURE_API_KEY": "fake-future-api-key-0123",
}
FAKE_AUTH = {
    "ANTHROPIC_API_KEY": "sk-ant-fake-owner-0123",
    "ANTHROPIC_AUTH_TOKEN": "fake-auth-token-0123",
    "CLAUDE_CODE_OAUTH_TOKEN": "fake-oauth-token-0123",
}


def _stub_cli(directory, dump_name="dump.json", name="claude"):
    """Исполняемая заглушка: пишет настоящее окружение и argv в JSON."""
    directory.mkdir(parents=True, exist_ok=True)
    dump = directory / dump_name
    stub = directory / name
    code = (
        "import json,os,sys;"
        f"json.dump({{'env':dict(os.environ),'argv':sys.argv[1:]}},open({str(dump)!r},'w'))"
    )
    stub.write_text(f"#!/bin/sh\nexec {sys.executable!r} -c {code!r} \"$@\"\n", encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return stub, dump


async def _process_env(bridge, tmp_path, **option_kwargs):
    """Окружение, которое получил процесс на настоящем пути запуска SDK."""
    from claude_agent_sdk import ClaudeAgentOptions
    from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

    stub, dump = _stub_cli(tmp_path / "stub")
    options = bridge._build_sdk_options(
        options_cls=ClaudeAgentOptions,
        project_path=str(tmp_path),
        session_id=None,
        **option_kwargs,
    )
    options = dataclasses.replace(options, cli_path=str(stub))
    transport = SubprocessCLITransport(prompt="hi", options=options)
    await transport.connect()
    await transport._process.wait()
    await transport.close()
    return json.loads(dump.read_text(encoding="utf-8"))


@pytest.fixture
def fake_process_env(monkeypatch):
    monkeypatch.setenv("CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK", "1")
    monkeypatch.setattr(ClaudeBridge, "_jail_available", staticmethod(lambda: False))
    for name, value in {**FAKE_SECRETS, **FAKE_AUTH}.items():
        monkeypatch.setenv(name, value)


def _assert_no_value(process_env, values):
    for value in values:
        leaked = [name for name, seen in process_env.items() if value in seen]
        assert not leaked, f"значение секрета в процессе под именами {leaked}"


@pytest.mark.parametrize(
    "option_kwargs",
    [{}, {"confine_root": "/tmp/project"}, {"anthropic_api_key": "sk-user-fake"}],
    ids=["regular", "confined", "user-key"],
)
async def test_process_env_has_no_panel_secrets(fake_process_env, tmp_path, option_kwargs):
    seen = await _process_env(ClaudeBridge(), tmp_path, **option_kwargs)
    _assert_no_value(seen["env"], FAKE_SECRETS.values())
    for name in FAKE_SECRETS:
        assert seen["env"].get(name) == ""


async def test_regular_process_keeps_owner_auth(fake_process_env, tmp_path):
    seen = await _process_env(ClaudeBridge(), tmp_path)
    for name, value in FAKE_AUTH.items():
        assert seen["env"][name] == value


async def test_confined_process_loses_owner_auth(fake_process_env, monkeypatch, tmp_path):
    monkeypatch.setattr(ClaudeBridge, "_subscription_creds_present", staticmethod(lambda: True))
    seen = await _process_env(ClaudeBridge(), tmp_path, confine_root=str(tmp_path))
    _assert_no_value(seen["env"], FAKE_AUTH.values())


async def test_user_key_survives_in_process(fake_process_env, monkeypatch, tmp_path):
    monkeypatch.setattr(ClaudeBridge, "_subscription_creds_present", staticmethod(lambda: True))
    seen = await _process_env(
        ClaudeBridge(), tmp_path, confine_root=str(tmp_path), anthropic_api_key="sk-user-fake"
    )
    assert seen["env"]["ANTHROPIC_API_KEY"] == "sk-user-fake"
    assert seen["env"]["AI_WORKSPACE_JAIL_NO_OWNER_CREDS"] == "1"


async def test_intentional_variables_are_not_blanked(fake_process_env, monkeypatch, tmp_path):
    seen = await _process_env(ClaudeBridge(extended_thinking=True), tmp_path)
    assert seen["env"]["PYTHONUTF8"] == "1"
    assert seen["env"]["MAX_THINKING_TOKENS"] == "8000"
    assert seen["env"]["PATH"] == os.environ["PATH"]


def test_spawn_env_blanks_only_what_cleaning_removed(monkeypatch):
    monkeypatch.setenv("KB_MCP_KEY", "fake-kb-key")
    monkeypatch.setenv("KB_MCP_URL", "https://kb.example.invalid/mcp")
    env = ClaudeBridge()._spawn_env()
    assert env["KB_MCP_KEY"] == ""
    assert env["KB_MCP_URL"] == ""


@pytest.mark.parametrize("confined", [False, True], ids=["regular", "confined"])
def test_clean_env_strips_kb_mcp_settings(monkeypatch, confined):
    monkeypatch.setenv("KB_MCP_KEY", "fake-kb-key")
    monkeypatch.setenv("KB_MCP_URL", "https://kb.example.invalid/mcp")
    env = ClaudeBridge._clean_env(confined=confined)
    assert "KB_MCP_KEY" not in env
    assert "KB_MCP_URL" not in env
