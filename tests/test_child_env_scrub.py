"""Подпроцессы вне SDK тоже не получают секреты панели.

Вместо настоящих программ в PATH стоит заглушка: она пишет своё окружение в файл,
поэтому проверяется то, что процесс получил на самом деле.
"""
from __future__ import annotations

import json

import pytest

from src.claude import commands
from src.claude.bridge import ClaudeBridge
from src.web import doc_preview
from tests.spawn_audit import spawn_audit  # noqa: F401
from tests.test_bridge_env_scrub import FAKE_SECRETS, _assert_no_value, _stub_cli

pytestmark = pytest.mark.usefixtures("spawn_audit")


@pytest.fixture
def stub_in_path(monkeypatch, tmp_path):
    for name, value in FAKE_SECRETS.items():
        monkeypatch.setenv(name, value)

    def _install(name: str):
        stub, dump = _stub_cli(tmp_path / f"bin-{name}", name=name)
        monkeypatch.setenv("PATH", str(stub.parent), prepend=":")
        return dump

    return _install


def _seen_env(dump) -> dict[str, str]:
    return json.loads(dump.read_text(encoding="utf-8"))["env"]


async def test_fetch_cli_slash_commands_gets_clean_env(stub_in_path):
    dump = stub_in_path("claude")
    await commands._fetch_cli_slash_commands(timeout=10)
    _assert_no_value(_seen_env(dump), FAKE_SECRETS.values())


async def test_fetch_cli_commands_for_project_gets_clean_env(stub_in_path, tmp_path):
    dump = stub_in_path("claude")
    commands._cli_cmd_cache.clear()
    await commands.fetch_cli_commands_for_project(str(tmp_path))
    _assert_no_value(_seen_env(dump), FAKE_SECRETS.values())


async def test_tmux_gets_clean_env(stub_in_path):
    """Первый вызов tmux поднимает сервер, а панели наследуют его окружение."""
    dump = stub_in_path("tmux")
    await ClaudeBridge(transport="tmux")._run_tmux("ls", check=False)
    _assert_no_value(_seen_env(dump), FAKE_SECRETS.values())


async def test_tmux_new_session_gets_clean_env(stub_in_path, tmp_path):
    dump = stub_in_path("tmux")
    bridge = ClaudeBridge(transport="tmux")
    await bridge._run_tmux("new-session", "-d", "-s", "s", "-c", str(tmp_path), check=False)
    assert json.loads(dump.read_text(encoding="utf-8"))["argv"][0] == "new-session"
    _assert_no_value(_seen_env(dump), FAKE_SECRETS.values())


def test_textutil_gets_clean_env(stub_in_path, tmp_path):
    dump = stub_in_path("textutil")
    source = tmp_path / "doc.rtf"
    source.write_text("x", encoding="utf-8")
    doc_preview._try_textutil(source)
    _assert_no_value(_seen_env(dump), FAKE_SECRETS.values())


def test_soffice_gets_clean_env(stub_in_path, tmp_path):
    dump = stub_in_path("soffice")
    source = tmp_path / "doc.docx"
    source.write_text("x", encoding="utf-8")
    doc_preview._try_soffice(source)
    _assert_no_value(_seen_env(dump), FAKE_SECRETS.values())
