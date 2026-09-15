"""GET /api/sessions/{uuid}/file?inline=1: PDF/картинки — inline, остальное attachment."""
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
    (proj / "report.pdf").write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    (proj / "note.docx").write_bytes(b"PK\x03\x04dummy-docx")
    (proj / "table.xlsx").write_bytes(b"PK\x03\x04dummy-xlsx")
    (proj / "page.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    (proj / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n")
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


def _session(sm: SessionManager, project_path: str):
    uid = sm.create_local_user(
        username="view", password_hash=hash_password("pw123456"), is_admin=False
    )
    sm.set_project_access(uid, project_path, "readonly")
    return sm.create_session(
        topic_id=-1, project_path=project_path, project_name="alpha", chat_id=uid
    )


def _disp(resp) -> str:
    return (resp.headers.get("content-disposition") or "").lower()


def _ctype(resp) -> str:
    return (resp.headers.get("content-type") or "").lower()


async def test_pdf_inline_sets_disposition_and_mime(setup):
    server, sm, pp = setup
    session = _session(sm, pp)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "view", "pw123456")
        resp = await c.get(
            f"/api/sessions/{session.session_uuid}/file",
            params={"path": "report.pdf", "inline": "1"},
        )
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    assert _disp(resp).startswith("inline")
    assert "application/pdf" in _ctype(resp)
    assert resp.headers.get("x-content-type-options") == "nosniff"


async def test_pdf_without_inline_is_attachment(setup):
    server, sm, pp = setup
    session = _session(sm, pp)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "view", "pw123456")
        resp = await c.get(
            f"/api/sessions/{session.session_uuid}/file",
            params={"path": "report.pdf"},
        )
    assert resp.status_code == 200
    assert _disp(resp).startswith("attachment")
    assert "octet-stream" in _ctype(resp)


async def test_docx_inline_stays_attachment(setup):
    server, sm, pp = setup
    session = _session(sm, pp)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "view", "pw123456")
        resp = await c.get(
            f"/api/sessions/{session.session_uuid}/file",
            params={"path": "note.docx", "inline": "1"},
        )
    assert resp.status_code == 200
    assert resp.content.startswith(b"PK")
    assert _disp(resp).startswith("attachment")
    assert "octet-stream" in _ctype(resp)


async def test_xlsx_inline_stays_attachment(setup):
    server, sm, pp = setup
    session = _session(sm, pp)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "view", "pw123456")
        resp = await c.get(
            f"/api/sessions/{session.session_uuid}/file",
            params={"path": "table.xlsx", "inline": "1"},
        )
    assert resp.status_code == 200
    assert _disp(resp).startswith("attachment")
    assert "octet-stream" in _ctype(resp)


async def test_html_inline_stays_attachment(setup):
    server, sm, pp = setup
    session = _session(sm, pp)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "view", "pw123456")
        resp = await c.get(
            f"/api/sessions/{session.session_uuid}/file",
            params={"path": "page.html", "inline": "1"},
        )
    assert resp.status_code == 200
    assert _disp(resp).startswith("attachment")


async def test_png_inline_is_image(setup):
    server, sm, pp = setup
    session = _session(sm, pp)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "view", "pw123456")
        resp = await c.get(
            f"/api/sessions/{session.session_uuid}/file",
            params={"path": "pic.png", "inline": "1"},
        )
    assert resp.status_code == 200
    assert _disp(resp).startswith("inline")
    assert "image/png" in _ctype(resp)


async def test_inline_requires_auth(setup):
    server, _sm, _pp = setup
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/api/sessions/00000000-0000-0000-0000-000000000000/file",
            params={"path": "report.pdf", "inline": "1"},
        )
    assert resp.status_code == 401
