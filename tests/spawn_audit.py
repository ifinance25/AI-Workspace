"""Второй рубеж стража: аудит-хук Python на запуск процессов.

AST-страж видит код, но его можно обойти (getattr, importlib, сторонняя библиотека).
Хук ловит сам запуск: события subprocess.Popen, os.posix_spawn, os.exec, os.spawn и
os.system. Пока включена фикстура spawn_audit, каждый запуск обязан передать env, и в
нём не должно быть непустых значений вне белого списка src/child_env.py.

Хук ставится один раз на процесс (снять его нельзя) и молчит вне фикстуры.
"""
from __future__ import annotations

import sys

import pytest

from src.child_env import (
    ALLOWED_NAMES,
    ALLOWED_PREFIXES,
    CLAUDE_AUTH_NAMES,
    CLAUDE_SETTING_NAMES,
)

# Значения, которые ставят намеренно: _spawn_env (кодировка, мышление, джейл) и SDK.
INTENTIONAL_NAMES = frozenset(
    {
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "MAX_THINKING_TOKENS",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_AGENT_SDK_VERSION",
        "PWD",  # SDK ставит рабочую папку запуска
    }
)
INTENTIONAL_PREFIXES = ("AI_WORKSPACE_",)
_ALLOWED = ALLOWED_NAMES | CLAUDE_SETTING_NAMES | CLAUDE_AUTH_NAMES | INTENTIONAL_NAMES

_state = {"active": False, "violations": []}


def _name(key: object) -> str:
    return key.decode() if isinstance(key, bytes) else str(key)


def _allowed(name: str) -> bool:
    return (
        name in _ALLOWED
        or name.startswith(ALLOWED_PREFIXES)
        or name.startswith(INTENTIONAL_PREFIXES)
    )


def _program(argv: object) -> str:
    if isinstance(argv, (list, tuple)) and argv:
        return _name(argv[0])
    return _name(argv)


def _check(event: str, argv: object, env: object) -> None:
    if env is None:
        _state["violations"].append(f"{event} {_program(argv)}: env не передан")
        return
    extra = sorted(
        _name(key)
        for key, value in dict(env).items()
        if value not in ("", b"") and not _allowed(_name(key))
    )
    if extra:
        _state["violations"].append(f"{event} {_program(argv)}: лишние имена {extra}")


def _hook(event: str, args: tuple) -> None:
    if not _state["active"]:
        return
    if event == "subprocess.Popen":
        _check(event, args[1], args[3])
    elif event in ("os.posix_spawn", "os.exec"):
        _check(event, args[1], args[2])
    elif event == "os.spawn":
        _check(event, args[2], args[3])
    elif event == "os.system":
        _state["violations"].append("os.system: окружение наследуется целиком")


sys.addaudithook(_hook)


@pytest.fixture
def spawn_audit():
    """Включает проверку на время теста; нарушения роняют тест в конце."""
    _state["violations"] = []
    _state["active"] = True
    try:
        yield _state["violations"]
    finally:
        _state["active"] = False
    assert not _state["violations"], "\n".join(_state["violations"])


def violations_during(action) -> list[str]:
    """Нарушения, которые хук записал за время action(): для самопроверки хука."""
    _state["violations"] = []
    _state["active"] = True
    try:
        action()
    finally:
        _state["active"] = False
    found, _state["violations"] = list(_state["violations"]), []
    return found
