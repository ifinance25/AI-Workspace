"""Личные подключения на настоящем Claude CLI: прокси в процессе панели.

Нужны вход в Claude и сеть, поэтому тесты запускаются только по явному флагу:
    RUN_REAL_CLAUDE=1 .venv/bin/python -m pytest tests/integration/test_connections_real_cli.py

Настоящий ClaudeBridge запускает настоящий claude. Тот вызывает mcp__github__get_me, а
прокси в панели ходит на поддельный GitHub MCP на 127.0.0.1, который пускает только с
правильным заголовком Authorization. Проверяется: инструмент сработал, маркер вернулся,
а токена нет ни в аргументах, ни в окружении процесса claude (как его видит ps).
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from src.claude.bridge import ClaudeBridge, ClaudeEventType
from src.connections import catalog
from src.connections.crypto import SecretBox
from src.connections.resolver import dispatch_mcp_servers
from src.connections.store import ConnectionsStore
from tests.connections.fake_upstream import (
    GITHUB_TOKEN,
    MARKER,
    NOTION_TOKEN,
    STDIO_MARKER,
    github_config,
    notion_config,
    serve_fake_github,
)
from tests.integration.test_kb_real_cli import FAKE_ENV, ProcessView, _watch
from tests.spawn_audit import allowing_names, spawn_audit  # noqa: F401

pytestmark = [
    pytest.mark.usefixtures("spawn_audit"),
    pytest.mark.skipif(
        os.environ.get("RUN_REAL_CLAUDE") != "1", reason="нужен RUN_REAL_CLAUDE=1, вход и сеть"
    ),
]

SDK_SETTINGS = SimpleNamespace(claude=SimpleNamespace(transport="sdk"))


@pytest.fixture
def panel_env(monkeypatch):
    """Окружение как у панели: фиктивные секреты рядом и пустые переменные входа."""
    for name in list(os.environ):
        if name.startswith("CLAUDE_") or name == "CLAUDECODE":
            monkeypatch.delenv(name)
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.setenv(name, "")
    for name, value in FAKE_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("ANTHROPIC_MODEL", "haiku")


@pytest.fixture
async def github():
    async with serve_fake_github() as fake:
        yield fake


def _point_catalog(monkeypatch, service_id: str, build) -> None:
    """Сервис из каталога, но с поддельным адресом или командой вместо настоящих."""
    original = catalog.get_service
    fake = dataclasses.replace(original(service_id), build_mcp_server=build)
    monkeypatch.setattr(
        "src.connections.resolver.catalog.get_service",
        lambda wanted: fake if wanted == service_id else original(wanted),
    )


async def _run(tmp_path, service_id: str, token: str, prompt: str):
    store = ConnectionsStore(tmp_path / "c.db", SecretBox(Fernet.generate_key().decode()))
    store.connect(user_id=1, service_id=service_id, secret=token)
    servers = dispatch_mcp_servers(1, store, SDK_SETTINGS, include_shared=False)
    assert servers and servers[service_id]["type"] == "sdk"
    project = tmp_path / "project"
    project.mkdir()
    view = ProcessView()
    watcher = asyncio.create_task(_watch(view, [token, *FAKE_ENV.values()]))
    events = []
    try:
        async for event in ClaudeBridge().send_message(
            message=prompt,
            topic_id=1,
            project_path=os.path.realpath(project),
            mcp_servers=servers,
        ):
            events.append(event)
    finally:
        watcher.cancel()
    text = "".join(e.content or "" for e in events if e.type == ClaudeEventType.TEXT)
    errors = [e.content for e in events if e.type == ClaudeEventType.ERROR]
    return text, errors, view


def _assert_process_clean(view: ProcessView) -> None:
    assert view.found, "процесс claude не найден в ps"
    assert view.env_visible, "ps не показал окружение процесса"
    assert not view.argv_has_secret
    assert not view.env_leaked


async def test_github_proxy_through_real_cli(panel_env, github, tmp_path, monkeypatch):
    _point_catalog(monkeypatch, "github", lambda secret: github_config(github.url, secret))
    prompt = "Вызови инструмент mcp__github__get_me и напиши значение поля marker из ответа."
    text, errors, view = await _run(tmp_path, "github", GITHUB_TOKEN, prompt)
    assert not errors
    assert github.rejected == []
    assert github.accepted > 0
    assert MARKER in text
    _assert_process_clean(view)


async def test_notion_stdio_proxy_through_real_cli(panel_env, tmp_path, monkeypatch):
    _point_catalog(monkeypatch, "notion", lambda secret: notion_config(secret))
    prompt = "Вызови инструмент mcp__notion__env_report и напиши значение поля marker из ответа."
    with allowing_names("NOTION_TOKEN"):
        text, errors, view = await _run(tmp_path, "notion", NOTION_TOKEN, prompt)
    assert not errors
    assert STDIO_MARKER in text
    _assert_process_clean(view)
