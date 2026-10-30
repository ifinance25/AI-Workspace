"""Веб-вход без Telegram передаёт флаг базы знаний так же, как src/bot/core.py.

Сервер не поднимается: подменённый WebServer запоминает аргументы и останавливает
_serve на start().
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest
import structlog

from src.config.settings import Settings

RUN_WEB = Path(__file__).resolve().parents[1] / "scripts" / "run_web.py"


class _Stop(Exception):
    pass


@pytest.fixture
def run_web():
    """scripts/run_web.py настраивает логи при импорте: возвращаем их обратно."""
    structlog_config = structlog.get_config()
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    spec = importlib.util.spec_from_file_location("run_web_under_test", RUN_WEB)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    structlog.configure(**structlog_config)
    root.handlers[:] = handlers
    root.setLevel(level)


async def _captured_kwargs(module, monkeypatch, tmp_path, *, url: str, key: str) -> dict:
    monkeypatch.setenv("KB_MCP_URL", url)
    monkeypatch.setenv("KB_MCP_KEY", key)
    monkeypatch.setenv("SESSION_DATABASE_PATH", str(tmp_path / "sessions.db"))
    settings = Settings(_env_file=None)
    settings.web.enabled = True
    settings.web.port = 8600
    monkeypatch.setattr(module, "_load_settings", lambda: settings)

    captured: dict = {}

    class FakeWebServer:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        async def start(self) -> None:
            raise _Stop

    monkeypatch.setattr("src.web.server.WebServer", FakeWebServer)
    with pytest.raises(_Stop):
        await module._serve(None, None)
    await captured["session_manager"].close()
    return captured


async def test_web_entry_enables_flag_when_configured(run_web, monkeypatch, tmp_path):
    kwargs = await _captured_kwargs(
        run_web,
        monkeypatch,
        tmp_path,
        url="https://kb.example.invalid/mcp",
        key="fake-kb-key",
    )
    assert kwargs["kb_search_enabled"] is True


@pytest.mark.parametrize(
    "url,key",
    [("", "fake-kb-key"), ("https://kb.example.invalid/mcp", ""), ("", "")],
    ids=["no-url", "no-key", "both-empty"],
)
async def test_web_entry_keeps_flag_off_without_config(run_web, monkeypatch, tmp_path, url, key):
    kwargs = await _captured_kwargs(run_web, monkeypatch, tmp_path, url=url, key=key)
    assert kwargs["kb_search_enabled"] is False
