"""Сквозная проверка на настоящем Claude CLI, модель haiku.

Нужны вход в Claude и сеть, поэтому тесты запускаются только по явному флагу:
    RUN_REAL_CLAUDE=1 .venv/bin/python -m pytest tests/integration/test_kb_real_cli.py

Настоящий ClaudeBridge запускает настоящий claude, а тот вызывает инструмент базы знаний
в процессе панели. Сервер на 127.0.0.1 проверяет запрос так же, как mcp/protocol.mjs.
Проверяется главное: инструмент вызван, маркер вернулся, а в аргументах и окружении
процесса claude нет ни адреса, ни ключа.

Проверки сравнивают значения и выводят только имена: окружение целиком в отчёт pytest
попасть не должно.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from src.child_env import child_env
from src.claude import commands
from src.claude.bridge import ClaudeBridge, ClaudeEventType
from src.connections.resolver import build_shared_mcp_servers
from tests.spawn_audit import spawn_audit  # noqa: F401

pytestmark = [pytest.mark.usefixtures("spawn_audit"), pytest.mark.skipif(
    os.environ.get("RUN_REAL_CLAUDE") != "1", reason="нужен RUN_REAL_CLAUDE=1, вход и сеть"
)]

KB_KEY = "fake-kb-key-e2e-0123456789"
MARKER = "KB-MARKER-7316-ORANGE"
FAKE_ENV = {
    "KB_MCP_KEY": KB_KEY,
    "WEB_JWT_SECRET": "fake-jwt-secret-e2e-0123",
    "TELEGRAM_BOT_TOKEN": "12345:fake-telegram-e2e",
    "CONNECTIONS_SECRET_KEY": "fake-connections-e2e-0123",
    "ADMIN_PASSWORD": "fake-admin-password-e2e",
    "MY_NEW_SERVICE_SECRET": "fake-new-service-e2e-0123",
}
SUPPORTED_VERSIONS = {
    "2025-11-25",
    "2026-07-28",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
    "2024-10-07",
}


@dataclass
class FakeServer:
    """Поведение validateMcpRequest из protocol.mjs плюс проверка ключа."""

    calls: list[dict] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    url: str = ""

    def _problem(self, request: web.Request, body: dict) -> str | None:
        headers = request.headers
        if request.path != "/mcp":
            return "path"
        if request.headers.get("Host") != self.url.split("/")[2]:
            return "host"
        if not headers.get("Content-Type", "").lower().startswith("application/json"):
            return "content-type"
        if "Origin" in headers:
            return "origin"
        if headers.get("Authorization") != f"Bearer {KB_KEY}":
            return "authorization"
        if headers.get("MCP-Protocol-Version") not in SUPPORTED_VERSIONS:
            return "protocol-version"
        if headers.get("Mcp-Method") != body.get("method"):
            return "mcp-method"
        if headers.get("Mcp-Name") != body.get("params", {}).get("name"):
            return "mcp-name"
        if "profile" in body.get("params", {}).get("arguments", {}):
            return "profile"
        return None

    async def handle(self, request: web.Request) -> web.Response:
        body = await request.json()
        problem = self._problem(request, body)
        if problem:
            self.rejected.append(problem)
            return web.Response(status=400)
        self.calls.append(body["params"])
        message = {
            "jsonrpc": "2.0",
            "id": body["id"],
            "result": {"content": [{"type": "text", "text": json.dumps({"marker": MARKER})}]},
        }
        return web.Response(
            text=f"event: message\ndata: {json.dumps(message)}\n\n",
            content_type="text/event-stream",
        )


@pytest.fixture
async def kb_server():
    fake = FakeServer()
    app = web.Application()
    app.router.add_post("/mcp", fake.handle)
    server = TestServer(app)
    await server.start_server()
    fake.url = str(server.make_url("/mcp"))
    yield fake
    await server.close()


@pytest.fixture
def panel_env(monkeypatch, kb_server):
    """Окружение как у панели: фиктивные значения и пустые переменные входа."""
    for name in list(os.environ):
        if name.startswith("CLAUDE_") or name == "CLAUDECODE":
            monkeypatch.delenv(name)
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"):
        monkeypatch.setenv(name, "")
    for name, value in FAKE_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("KB_MCP_URL", kb_server.url)
    monkeypatch.setenv("ANTHROPIC_MODEL", "haiku")


class _Settings:
    def __init__(self, url: str) -> None:
        self._url = url

    def get_kb_mcp_url(self) -> str:
        return self._url

    def get_kb_mcp_key(self) -> str:
        return KB_KEY


@dataclass
class ProcessView:
    found: bool = False
    argv_has_secret: bool = False
    env_visible: bool = False
    env_leaked: list[str] = field(default_factory=list)


async def _output(*command: str) -> str:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=child_env(),
    )
    stdout, _ = await process.communicate()
    return stdout.decode("utf-8", errors="replace")


async def _watch(view: ProcessView, values: list[str]) -> None:
    """Смотрит на процесс claude снаружи, как ps auxww у любого пользователя машины."""
    while True:
        for line in (await _output("ps", "-axww", "-o", "pid=,command=")).splitlines():
            pid, _, command = line.strip().partition(" ")
            # Только claude из SDK панели, а не другие процессы claude на машине.
            if not command.split(" ")[0].endswith("claude_agent_sdk/_bundled/claude"):
                continue
            view.found = True
            view.argv_has_secret |= any(value in line for value in values)
            with_env = await _output("ps", "eww", "-p", pid)
            view.env_visible |= "PATH=" in with_env
            view.env_leaked += [value[:12] for value in values if value in with_env]
        await asyncio.sleep(0.2)


async def _run(
    bridge: ClaudeBridge, kb_server: FakeServer, tmp_path, prompt: str, *, with_kb=True, **kwargs
):
    project = os.path.realpath(tmp_path)
    servers = build_shared_mcp_servers(_Settings(kb_server.url), user_id=1) if with_kb else None
    assert servers or not with_kb, "запись базы знаний не собрана"
    view = ProcessView()
    values = [*FAKE_ENV.values(), kb_server.url, kb_server.url.split("/")[2]]
    watcher = asyncio.create_task(_watch(view, values))
    events = []
    try:
        async for event in bridge.send_message(
            message=prompt, topic_id=1, project_path=project, mcp_servers=servers, **kwargs
        ):
            events.append(event)
    finally:
        watcher.cancel()
    text = "".join(e.content or "" for e in events if e.type == ClaudeEventType.TEXT)
    errors = [e.content for e in events if e.type == ClaudeEventType.ERROR]
    return text, errors, view


CALL_PROMPT = (
    "Вызови инструмент mcp__fakt_kb__search_project с query \"проверка\" "
    "и напиши значение поля marker из ответа."
)


def _assert_kb_worked(kb_server: FakeServer, text: str, errors: list, view: ProcessView) -> None:
    assert not errors
    assert not kb_server.rejected
    assert [call["name"] for call in kb_server.calls] == ["search_project"]
    assert MARKER in text
    assert view.found, "процесс claude не найден в ps"
    assert view.env_visible, "ps не показал окружение процесса"
    assert not view.argv_has_secret
    assert not view.env_leaked


async def test_regular_session(panel_env, kb_server, tmp_path):
    text, errors, view = await _run(ClaudeBridge(), kb_server, tmp_path, CALL_PROMPT)
    _assert_kb_worked(kb_server, text, errors, view)


async def test_confined_session(panel_env, kb_server, tmp_path, monkeypatch):
    monkeypatch.setattr(ClaudeBridge, "_subscription_creds_present", staticmethod(lambda: True))
    text, errors, view = await _run(
        ClaudeBridge(), kb_server, tmp_path, CALL_PROMPT, confine_root=os.path.realpath(tmp_path)
    )
    _assert_kb_worked(kb_server, text, errors, view)


async def test_permission_mode_default(panel_env, kb_server, tmp_path):
    """Без разрешения на mcp__fakt_kb__* в этом режиме инструмент был бы отклонён."""
    bridge = ClaudeBridge(permission_mode="default")
    text, errors, view = await _run(bridge, kb_server, tmp_path, CALL_PROMPT)
    _assert_kb_worked(kb_server, text, errors, view)


async def test_readonly_session(panel_env, kb_server, tmp_path):
    text, errors, view = await _run(ClaudeBridge(), kb_server, tmp_path, CALL_PROMPT, readonly=True)
    _assert_kb_worked(kb_server, text, errors, view)


async def test_cli_fallback_keeps_login(panel_env, tmp_path):
    """Запасной путь: настоящий claude из PATH с тем же белым списком."""
    bridge = ClaudeBridge()
    events = [
        event
        async for event in bridge._send_message_via_cli(
            message="Ответь одним словом: привет",
            topic_id=1,
            project_path=os.path.realpath(tmp_path),
            session_id=None,
        )
    ]
    # Ошибку здесь не проверяем: монитор CLI-пути срабатывает на слове Killed в служебном
    # выводе, и с полным окружением точно так же. Для входа важен сам ответ модели.
    assert "".join(e.content or "" for e in events if e.type == ClaudeEventType.TEXT).strip()


async def test_slash_commands_fetch_keeps_login(panel_env):
    assert await commands._fetch_cli_slash_commands(timeout=60)


async def test_kb_mode_has_no_bash(panel_env, kb_server, tmp_path):
    """Лупа включена: Bash недоступен, а инструмент базы работает в том же запуске."""
    prompt = (
        "Сначала выполни в Bash команду `echo BASH-RAN-4417 > bash.txt`. "
        "Потом вызови mcp__fakt_kb__search_project с query \"проверка\" и напиши marker."
    )
    text, errors, view = await _run(ClaudeBridge(), kb_server, tmp_path, prompt)
    assert not (tmp_path / "bash.txt").exists()
    _assert_kb_worked(kb_server, text, errors, view)


async def test_bash_inside_session_sees_nothing(panel_env, kb_server, tmp_path):
    """printenv из задачи ревью. Скрипт пишет тест, модель только запускает его: просьбу
    вывести переменные напрямую модель может отклонить, и это ничего бы не доказало."""
    names = [*FAKE_ENV, "KB_MCP_URL"]
    script = "\n".join(f'echo "{name}=[$(printenv {name})]"' for name in names)
    (tmp_path / "check.sh").write_text(script + "\necho finished\n", encoding="utf-8")
    prompt = "Выполни в Bash команду `sh check.sh > out.txt` и ответь одним словом: готово."
    text, errors, view = await _run(ClaudeBridge(), kb_server, tmp_path, prompt, with_kb=False)
    out = (tmp_path / "out.txt").read_text(encoding="utf-8")
    assert not errors
    assert "finished" in out and "KB_MCP_KEY=[]" in out
    leaked = [name for name, value in FAKE_ENV.items() if value in out or value in text]
    assert not leaked
    assert kb_server.url not in out
    assert view.found and view.env_visible
    assert not view.env_leaked
