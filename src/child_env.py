"""Окружение подпроцессов панели: только белый список.

systemd кладёт .env в окружение процесса панели, поэтому всё, что запускает панель,
по умолчанию наследует её секреты. Маска секретов здесь не годится: KB_MCP_KEY прошёл
мимо неё только потому, что она не знала нового имени. Новая переменная с любым именем
по умолчанию не проходит, а имя в список добавляется явно.

Запуск без env= роняет tests/test_subprocess_env_guard.py.
"""
from __future__ import annotations

import os

# Без них не работают программы и Bash внутри Claude. Только пути и язык, без значений,
# которые дают доступ к чему-либо.
ALLOWED_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "TERM",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LANG",
        "LANGUAGE",
        "TZ",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
        # Свой корневой сертификат за корпоративным TLS: без него нет входа.
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "NODE_EXTRA_CA_CERTS",
    }
)
ALLOWED_PREFIXES = ("LC_",)

# Настройки самого Claude, не секреты.
CLAUDE_SETTING_NAMES = frozenset({"CLAUDE_CONFIG_DIR", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL"})

# Вход Claude. Идут только в процесс claude и только если сессии они положены.
CLAUDE_AUTH_NAMES = frozenset(
    {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"}
)


def child_env(*, claude: bool = False, owner_auth: bool = False) -> dict[str, str]:
    """Окружение подпроцесса: всё, что не в списке, не передаётся.

    claude добавляет настройки Claude, owner_auth добавляет вход владельца.
    """
    allowed = set(ALLOWED_NAMES)
    if claude:
        allowed |= CLAUDE_SETTING_NAMES
    if owner_auth:
        allowed |= CLAUDE_AUTH_NAMES
    return {
        name: value
        for name, value in os.environ.items()
        if name in allowed or name.startswith(ALLOWED_PREFIXES)
    }


def blank_the_rest(env: dict[str, str]) -> dict[str, str]:
    """Обнуляет всё остальное из os.environ.

    SDK собирает окружение как {**os.environ, ..., **options.env}: отсутствие имени в
    options.env ничего не даёт, значение вернётся из os.environ. Пустая строка побеждает
    при слиянии.
    """
    return {**dict.fromkeys(os.environ, ""), **env}


def claude_env(*, owner_auth: bool = True) -> dict[str, str]:
    """Окружение процесса claude: единственный способ его собрать вне ClaudeBridge."""
    return blank_the_rest(child_env(claude=True, owner_auth=owner_auth))
