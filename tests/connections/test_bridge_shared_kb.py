"""Мост и база знаний ФАКТ: запись типа sdk работает только на пути SDK.

Сервер живёт в процессе панели, поэтому в аргументы claude не попадает ни адрес, ни
ключ. На запасном CLI-пути такой записи некуда деться: она отбрасывается, и подсказка
модели там не появляется.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sys

import pytest
from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport

from src.claude.bridge import READONLY_DISALLOWED_TOOLS, ClaudeBridge
from src.connections.kb_tools import build_kb_server
from tests.spawn_audit import spawn_audit  # noqa: F401

pytestmark = pytest.mark.usefixtures("spawn_audit")

KB_KEY = "fake-kb-key-0123456789"
KB_URL = "https://kb.example.invalid/fake-path"
NOTION_SERVER = {"command": "npx", "args": [], "env": {"NOTION_TOKEN": "x"}}
HINT_MARKER = "mcp__fakt_kb__"


@pytest.fixture
def kb_server() -> dict:
    return build_kb_server(KB_URL, KB_KEY)


def _sdk_options(bridge: ClaudeBridge, mcp_servers, **kwargs) -> ClaudeAgentOptions:
    return bridge._build_sdk_options(
        options_cls=ClaudeAgentOptions,
        project_path="/tmp",
        session_id=None,
        mcp_servers=mcp_servers,
        **kwargs,
    )


def _sdk_append(bridge: ClaudeBridge, mcp_servers) -> str:
    return _sdk_options(bridge, mcp_servers).system_prompt["append"]


def _argv(options: ClaudeAgentOptions) -> list[str]:
    """Настоящие аргументы процесса claude на пути SDK."""
    options = dataclasses.replace(options, cli_path="/bin/true")
    return SubprocessCLITransport(prompt="hi", options=options)._build_command()


def _cli_append(args: list[str]) -> str:
    return args[args.index("--append-system-prompt") + 1]


def _flag_values(args: list[str], flag: str) -> list[str]:
    return [args[i + 1] for i, part in enumerate(args) if part == flag]


# --- Подсказка: только при реально подключённом сервере -----------------------


def test_sdk_hint_present_with_shared_kb(kb_server):
    assert HINT_MARKER in _sdk_append(ClaudeBridge(), {"fakt_kb": kb_server})


def test_sdk_hint_covers_all_points(kb_server):
    append = _sdk_append(ClaudeBridge(), {"fakt_kb": kb_server})
    for needle in (
        "ФАКТ",
        "ФТТ",
        "ПМИ",
        "матрица соответствия",
        "Redmine",
        "Bitrix24",
        "других проектах",
        "только читают",
        "данные",
        "не инструкция",
        "fragment_id",
        "не ищи ответ в файлах проекта",
    ):
        assert needle in append, needle


def test_hint_does_not_mention_profile(kb_server):
    assert "profile" not in _sdk_append(ClaudeBridge(), {"fakt_kb": kb_server})


@pytest.mark.parametrize(
    "mcp_servers",
    [None, {}, {"notion": NOTION_SERVER}],
    ids=["none", "empty", "personal-only"],
)
def test_sdk_hint_absent_without_shared_kb(mcp_servers):
    assert HINT_MARKER not in _sdk_append(ClaudeBridge(), mcp_servers)


def test_sdk_hint_present_alongside_personal_servers(kb_server):
    servers = {"notion": NOTION_SERVER, "fakt_kb": kb_server}
    assert HINT_MARKER in _sdk_append(ClaudeBridge(), servers)


def test_base_prompt_stays_without_shared_kb():
    bridge = ClaudeBridge()
    assert bridge._system_prompt_append(shared_kb=True).startswith(bridge._system_prompt_append())


def test_cli_args_have_no_hint():
    args = ClaudeBridge()._build_cli_args(message="hi", session_id=None)
    assert HINT_MARKER not in _cli_append(args)


# --- SDK: разрешение только на инструменты базы -------------------------------


@pytest.mark.parametrize("mode", ["bypassPermissions", "default", "acceptEdits"])
def test_sdk_allows_only_kb_tools(kb_server, mode):
    options = _sdk_options(ClaudeBridge(permission_mode=mode), {"fakt_kb": kb_server})
    assert options.allowed_tools == ["mcp__fakt_kb__*"]
    assert _flag_values(_argv(options), "--allowedTools") == ["mcp__fakt_kb__*"]


@pytest.mark.parametrize(
    "mcp_servers", [None, {"notion": NOTION_SERVER}], ids=["none", "personal-only"]
)
def test_sdk_allows_nothing_extra_without_shared_kb(mcp_servers):
    options = _sdk_options(ClaudeBridge(permission_mode="default"), mcp_servers)
    assert options.allowed_tools == []
    assert "--allowedTools" not in _argv(options)


def test_sdk_readonly_keeps_builtin_ban_and_allows_kb(kb_server):
    options = _sdk_options(ClaudeBridge(), {"fakt_kb": kb_server}, readonly=True)
    assert set(READONLY_DISALLOWED_TOOLS) <= set(options.disallowed_tools)
    assert options.allowed_tools == ["mcp__fakt_kb__*"]
    assert not any(tool.startswith("mcp__") for tool in READONLY_DISALLOWED_TOOLS)


# --- SDK: что уходит в аргументы процесса --------------------------------------


def test_sdk_argv_has_neither_url_nor_key(kb_server):
    argv = _argv(_sdk_options(ClaudeBridge(), {"fakt_kb": kb_server}))
    joined = " ".join(argv)
    assert KB_KEY not in joined
    assert KB_URL not in joined
    assert "kb.example.invalid" not in joined


def test_sdk_mcp_config_holds_only_name_and_type(kb_server):
    argv = _argv(_sdk_options(ClaudeBridge(), {"fakt_kb": kb_server}))
    config = json.loads(_flag_values(argv, "--mcp-config")[0])
    assert config == {"mcpServers": {"fakt_kb": {"type": "sdk", "name": "fakt_kb"}}}


# --- Запасной CLI-путь: записи sdk на него не идут --------------------------------


def test_temp_config_skips_sdk_record(kb_server):
    assert ClaudeBridge()._write_temp_mcp_config({"fakt_kb": kb_server}) is None


def test_temp_config_skips_personal_proxy_records(kb_server):
    """Личные подключения теперь тоже записи sdk (прокси в панели): на запасной CLI-путь
    они не идут, и файла с расшифрованным токеном нет."""
    from src.connections.proxy import build_proxy_server

    notion = build_proxy_server("notion", NOTION_SERVER)
    assert ClaudeBridge()._write_temp_mcp_config({"fakt_kb": kb_server, "notion": notion}) is None


def _record_cli_run(monkeypatch, bridge: ClaudeBridge) -> dict:
    captured: dict = {}
    real_build = bridge._build_cli_args

    def _spy(**kwargs):
        captured["args"] = real_build(**kwargs)
        path = kwargs.get("mcp_config_path")
        captured["config_path"] = path
        if path:
            with open(path, encoding="utf-8") as fh:
                captured["config"] = json.load(fh)
        return [sys.executable, "-c", "pass"]

    monkeypatch.setattr(bridge, "_build_cli_args", _spy)
    return captured


async def _run_cli(bridge: ClaudeBridge, mcp_servers, **kwargs) -> None:
    async for _ in bridge._send_message_via_cli(
        message="hi",
        topic_id=1,
        project_path=os.getcwd(),
        session_id=None,
        mcp_servers=mcp_servers,
        **kwargs,
    ):
        pass


async def test_cli_run_with_sdk_record_only(monkeypatch, kb_server):
    bridge = ClaudeBridge()
    captured = _record_cli_run(monkeypatch, bridge)
    await _run_cli(bridge, {"fakt_kb": kb_server})
    assert captured["config_path"] is None
    assert "--mcp-config" not in captured["args"]
    assert HINT_MARKER not in _cli_append(captured["args"])


async def test_cli_run_keeps_personal_servers_without_kb(monkeypatch, kb_server):
    bridge = ClaudeBridge()
    captured = _record_cli_run(monkeypatch, bridge)
    await _run_cli(bridge, {"fakt_kb": kb_server, "notion": NOTION_SERVER})
    assert captured["config"] == {"mcpServers": {"notion": NOTION_SERVER}}
    assert not os.path.exists(captured["config_path"])
    assert HINT_MARKER not in _cli_append(captured["args"])


@pytest.mark.parametrize("readonly", [False, True], ids=["full", "readonly"])
async def test_cli_run_has_no_kb_allowed_tools(monkeypatch, kb_server, readonly):
    bridge = ClaudeBridge(permission_mode="bypassPermissions")
    captured = _record_cli_run(monkeypatch, bridge)
    await _run_cli(bridge, {"fakt_kb": kb_server}, readonly=readonly)
    assert "--allowedTools" not in captured["args"]
    assert not any("fakt_kb" in part for part in captured["args"])


# --- Лупа включена: в запуске только инструменты базы ----------------------------


@pytest.mark.parametrize("confine_root", [None, "/tmp/project"], ids=["regular", "confined"])
def test_kb_run_has_no_builtin_tools(kb_server, confine_root):
    options = _sdk_options(ClaudeBridge(), {"fakt_kb": kb_server}, confine_root=confine_root)
    assert options.tools == []
    argv = _argv(options)
    assert _flag_values(argv, "--tools") == [""]
    assert "--strict-mcp-config" in argv


def test_kb_run_bans_every_known_builtin(kb_server):
    options = _sdk_options(ClaudeBridge(), {"fakt_kb": kb_server})
    for name in (
        "Bash", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep", "LS",
        "WebFetch", "WebSearch", "Task", "Agent", "TodoWrite", "Skill", "ToolSearch",
        "Monitor", "Workflow", "SendMessage", "CronCreate", "TaskCreate", "EnterWorktree",
    ):
        assert name in options.disallowed_tools, name
    assert not any(name.startswith("mcp__fakt_kb") for name in options.disallowed_tools)


def test_kb_run_drops_other_mcp_servers(kb_server):
    options = _sdk_options(ClaudeBridge(), {"fakt_kb": kb_server, "notion": NOTION_SERVER})
    assert set(options.mcp_servers) == {"fakt_kb"}
    config = json.loads(_flag_values(_argv(options), "--mcp-config")[0])
    assert set(config["mcpServers"]) == {"fakt_kb"}


def test_kb_run_readonly_keeps_full_ban(kb_server):
    options = _sdk_options(ClaudeBridge(), {"fakt_kb": kb_server}, readonly=True)
    assert set(READONLY_DISALLOWED_TOOLS) <= set(options.disallowed_tools)
    assert "Read" in options.disallowed_tools


async def _pre_tool_decision(options, tool_name: str) -> dict:
    """Решение PreToolUse всех хуков запуска для инструмента."""
    for matcher in options.hooks["PreToolUse"]:
        for hook in matcher.hooks:
            result = await hook({"tool_name": tool_name, "tool_input": {}}, None, None)
            if result:
                return result
    return {}


@pytest.mark.parametrize(
    "tool", ["Bash", "Read", "WebFetch", "Task", "mcp__notion__search", "mcp__fakt_kbx__x"]
)
async def test_kb_run_hook_denies_everything_else(kb_server, tool):
    options = _sdk_options(ClaudeBridge(), {"fakt_kb": kb_server})
    decision = await _pre_tool_decision(options, tool)
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


async def test_kb_run_hook_lets_kb_tools_through(kb_server, tmp_path):
    options = _sdk_options(ClaudeBridge(), {"fakt_kb": kb_server}, confine_root=str(tmp_path))
    assert await _pre_tool_decision(options, "mcp__fakt_kb__search_project") == {}


def test_kb_hint_says_only_kb_is_available(kb_server):
    assert "доступна только база знаний" in _sdk_append(ClaudeBridge(), {"fakt_kb": kb_server})


def test_run_without_kb_keeps_tools(kb_server):
    options = _sdk_options(ClaudeBridge(), {"notion": NOTION_SERVER})
    assert options.tools is None
    assert "Bash" not in options.disallowed_tools
    assert not options.strict_mcp_config
