"""Поддельные сервисы для тестов прокси «Подключений».

HTTP: настоящий MCP-сервер (streamable HTTP) на 127.0.0.1, как удалённый GitHub MCP. Он
пускает только запрос с правильным заголовком Authorization, остальные получают 401 и
попадают в rejected.

stdio: этот же файл, запущенный как скрипт, работает как MCP-сервер Notion по stdio и
отчитывается, какие имена окружения он получил и совпал ли токен.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

GITHUB_TOKEN = "ghp_FAKE_TEST_TOKEN_123"
NOTION_TOKEN = "ntn_FAKE_TEST_TOKEN_456"
MARKER = "GH-MARKER-5521-TEAL"
STDIO_MARKER = "NOTION-MARKER-8810-PLUM"
TOOL_TITLE = "Кто я"


def _build_github_server():
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer("fake-github")

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=True, title=TOOL_TITLE, openWorldHint=False)
    )
    def get_me() -> str:
        """Профиль владельца токена."""
        return json.dumps({"login": "octocat", "marker": MARKER})

    @server.tool()
    def add(a: int, b: int) -> str:
        """Сумма двух чисел."""
        return str(a + b)

    return server


@dataclass
class FakeGithub:
    url: str = ""
    rejected: list[str] = field(default_factory=list)
    accepted: int = 0


def _guarded(app, fake: FakeGithub, token: str):
    from starlette.responses import JSONResponse

    expected = f"Bearer {token}".encode()

    async def guarded(scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            if headers.get(b"authorization") != expected:
                fake.rejected.append(scope["method"])
                response = JSONResponse({"error": "unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return
            fake.accepted += 1
        await app(scope, receive, send)

    return guarded


@asynccontextmanager
async def serve_fake_github(token: str = GITHUB_TOKEN) -> AsyncIterator[FakeGithub]:
    """MCP-сервер на свободном порту 127.0.0.1 на время блока."""
    import uvicorn

    fake = FakeGithub()
    app = _build_github_server().streamable_http_app(stateless_http=True, json_response=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    config = uvicorn.Config(_guarded(app, fake, token), log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # uvicorn < 0.29
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started:
            if task.done():
                task.result()
            await asyncio.sleep(0.01)
        fake.url = f"http://127.0.0.1:{port}/mcp"
        yield fake
    finally:
        server.should_exit = True
        await task
        sock.close()


def github_config(url: str, token: str | None = GITHUB_TOKEN) -> dict:
    """Запись как у catalog._github, только с адресом поддельного сервера."""
    config: dict = {"type": "http", "url": url}
    if token is not None:
        config["headers"] = {"Authorization": f"Bearer {token}"}
    return config


def notion_config(token: str = NOTION_TOKEN) -> dict:
    """Запись как у catalog._notion, только с этим скриптом вместо npx."""
    return {
        "command": sys.executable,
        "args": [os.path.abspath(__file__)],
        "env": {"NOTION_TOKEN": token},
    }


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _run_stdio() -> None:
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer("fake-notion")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def env_report() -> str:
        """Имена окружения и отпечаток токена, без значений."""
        token = os.environ.get("NOTION_TOKEN", "")
        return json.dumps(
            {
                "names": sorted(os.environ),
                "token_sha256": token_digest(token),
                "marker": STDIO_MARKER,
            }
        )

    server.run()


if __name__ == "__main__":
    _run_stdio()
