"""GET /api/files/doc-preview: HTML для .doc, ошибка на мусоре, кириллическое имя."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.web.passwords import hash_password
from src.web.server import WebServer


def _rtf(text: str) -> bytes:
    body = []
    for ch in text:
        o = ord(ch)
        if o < 128:
            body.append(ch)
        else:
            body.append("".join(f"\\'{b:02x}" for b in ch.encode("cp1251")))
    return (r"{\rtf1\ansi\ansicpg1251\pard " + "".join(body) + r"\par}").encode("ascii")


@pytest.fixture
def tmp_dir():
    path = Path(tempfile.mkdtemp())
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def setup(tmp_dir):
    bus = EventBus()
    sm = SessionManager(storage_path=tmp_dir / "sessions.db")
    proj = tmp_dir / "alpha"
    proj.mkdir()
    (proj / "note.doc").write_bytes(_rtf("Привет из .doc"))
    (proj / "документ.Док").write_bytes(_rtf("Кириллица"))
    (proj / "bad.doc").write_bytes(b"\x00\x01not-a-doc")
    (proj / "note.docx").write_bytes(b"PK\x03\x04dummy")
    settings = WebSettings(
        enabled=True, host="127.0.0.1", port=0, jwt_secret="x" * 32,
        telegram_bot_username="t",
    )
    server = WebServer(
        settings=settings, allowed_user_ids=[100], bot_username="t",
        session_manager=sm, event_bus=bus, bot_token="12345:abc",
        jwt_secret="x" * 32, project_paths=[proj],
    )
    try:
        yield server, sm, str(proj)
    finally:
        sm.close_sync()
        sm._engine.sync_engine.dispose()


async def _login(c: AsyncClient, username: str, password: str) -> None:
    r = await c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text


def _user(sm: SessionManager, project_path: str) -> None:
    uid = sm.create_local_user(
        username="view", password_hash=hash_password("pw123456"), is_admin=False
    )
    sm.set_project_access(uid, project_path, "readonly")


async def test_doc_preview_returns_html(setup):
    server, sm, pp = setup
    _user(sm, pp)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "view", "pw123456")
        resp = await c.get(
            "/api/files/doc-preview",
            params={"project_path": pp, "rel": "note.doc"},
        )
    assert resp.status_code == 200, resp.text
    html = resp.json()["html"]
    assert "Привет" in html
    assert "<script>" not in html


async def test_doc_preview_cyrillic_ext(setup):
    server, sm, pp = setup
    _user(sm, pp)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "view", "pw123456")
        resp = await c.get(
            "/api/files/doc-preview",
            params={"project_path": pp, "rel": "документ.Док"},
        )
    assert resp.status_code == 200, resp.text
    assert "Кириллица" in resp.json()["html"]


async def test_doc_preview_garbage_is_422(setup):
    server, sm, pp = setup
    _user(sm, pp)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "view", "pw123456")
        resp = await c.get(
            "/api/files/doc-preview",
            params={"project_path": pp, "rel": "bad.doc"},
        )
    assert resp.status_code == 422, resp.text
    assert "Скачайте" in resp.json()["detail"]


async def test_doc_preview_rejects_docx_name(setup):
    server, sm, pp = setup
    _user(sm, pp)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "view", "pw123456")
        resp = await c.get(
            "/api/files/doc-preview",
            params={"project_path": pp, "rel": "note.docx"},
        )
    assert resp.status_code == 400, resp.text


async def test_doc_preview_requires_auth(setup):
    server, _sm, pp = setup
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/api/files/doc-preview",
            params={"project_path": pp, "rel": "note.doc"},
        )
    assert resp.status_code == 401
