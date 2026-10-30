"""Файрвол ограниченных сессий: окружение панели и выход из корня через cd.

Без джейла `ps axeww` показывает окружение панели, `printenv` отдаёт ключ владельца,
а пути в команде разрешаются от корня проекта, поэтому `cd` уводил проверку в сторону.
Команда разбирается по ; && || | & скобкам и переводам строк, каждая часть отдельно.
"""
from __future__ import annotations

import pytest

from src.bot.middleware.security import SecurityMiddleware, SecurityViolation
from src.claude.tool_firewall import firewall_check


@pytest.fixture
def root(tmp_path):
    project = tmp_path / "project"
    (project / "sub" / "deep").mkdir(parents=True)
    return project


def _bash(root, command: str) -> None:
    middleware = SecurityMiddleware(allowed_roots=[root], audit_log_path=root.parent / "sec.log")
    middleware.validate_tool_use(
        tool_name="Bash", tool_input={"command": command}, project_root=str(root)
    )


def _category(root, command: str) -> str:
    with pytest.raises(SecurityViolation) as exc:
        _bash(root, command)
    return exc.value.category


@pytest.mark.parametrize(
    "command",
    [
        "ps axeww",
        "ps",
        "/bin/ps aux",
        'p"s" aux',
        "p\\s aux",
        "ls; ps",
        "ls;ps",
        "ls && ps e",
        "ls || ps",
        "ls | ps",
        "ls & ps",
        "ls\nps",
        "(ps)",
        "{ ps; }",
        "nohup ps",
        "sudo ps",
        "command ps",
        "xargs -0 ps",
        "timeout 5 ps",
        "pgrep -fl claude",
        "pkill -f claude",
        "top -l 1",
        "htop",
        "printenv",
        "printenv ANTHROPIC_API_KEY",
        "env",
        "env | grep KEY",
        "env FOO=1 ls",
        "/usr/bin/env",
        "compgen -v",
        "eval ps",
        "export",
        "export -p",
        "ls; export",
        "declare -x",
        "declare -p",
        "declare",
        "typeset -x",
        "set",
        "ls && set",
    ],
)
def test_environment_dump_is_blocked(root, command):
    assert _category(root, command) == "env_dump"


@pytest.mark.parametrize(
    "command",
    [
        "cat /proc/self/environ",
        "cat /proc/1/cmdline",
        "ls /proc",
        "tr '\\0' '\\n' < /PROC/self/environ",
        "grep -a KEY environ",
        "strings ./environ.bin",
    ],
)
def test_proc_and_environ_are_blocked(root, command):
    assert _category(root, command) == "env_dump"


@pytest.mark.parametrize(
    "command",
    [
        "cd",
        "cd ~",
        "cd ~/",
        "cd ~root",
        "cd -",
        "cd ..",
        "cd /",
        "cd /etc",
        "cd ../..",
        "cd; cat .claude/.credentials.json",
        "cd ..;cd ..;cd ..; cat opt/ai-workspace/.en?",
        "cd sub && cd ../..",
        "cd sub; cd deep; cd ../../..",
        "pushd /etc",
        "pushd ..",
        "pushd",
        "chdir ..",
        "cd -P ..",
        "CDPATH=/ cd etc",
        "HOME=/ cd",
        "ls && cd /tmp",
        "(cd ..; ls)",
    ],
)
def test_leaving_project_root_with_cd_is_blocked(root, command):
    assert _category(root, command) in {"cd_outside_root", "path_traversal"}


@pytest.mark.parametrize(
    "command",
    [
        "cd sub/deep || cat ../../x",
        "cd sub/deep; cat ../../../x",
        "cd sub/deep && true || cat ../../x",
        "cd sub/deep | cat ../../x",
    ],
)
def test_failed_cd_cannot_hide_a_path_outside_root(root, command):
    """cd может не сработать: путь проверяется и от корня, и от новой папки."""
    assert _category(root, command) == "path_traversal"


@pytest.mark.parametrize(
    "command",
    [
        "cat .en?",
        "cat .e*",
        "cat sub/.env*",
        "cat *.env",
        "cat .e[n]v",
        "cat .[e]nv",
        "cat .cred*",
        "cat .claude/.cred*",
        "ls .ss?",
        "cat .ss?/id_r*",
        "cat .{env,x}",
        "cat .e{n,x}v",
        "cat id_r?a",
        "cat .git-cred*",
    ],
)
def test_glob_that_can_reach_secrets_is_blocked(root, command):
    assert _category(root, command) == "sensitive_glob"


@pytest.mark.parametrize(
    "command",
    [
        "ls",
        "ls -la",
        "cat README.md",
        "cd sub && ls",
        "cd sub; cat file.txt",
        "cd ./sub/deep",
        "cd sub/deep && cat ../file.txt",
        "(cd sub && cat ../file.txt)",
        "pushd sub",
        "popd",
        "git status | grep modified",
        "echo hello > out.txt",
        "ls *.py",
        "cat src/*.ts",
        "export FOO=1",
        "set -e",
        "declare -a items",
        "echo 'ps is a tool'",
        "pytest -q tests",
        "npm test",
    ],
)
def test_ordinary_commands_still_pass(root, command):
    _bash(root, command)


def test_firewall_check_reports_reason(root):
    reason = firewall_check("Bash", {"command": "ps axeww"}, root)
    assert reason and "env_dump" in reason


def test_non_confined_session_is_untouched(root):
    """Правила только для ограниченных сессий: без корня файрвол не вмешивается."""
    assert firewall_check("Bash", {"command": "ps axeww"}, None) is None
