"""POST /api/files/upload: авторизация, traversal, несколько файлов."""
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
    (tmp_dir / "alpha").mkdir()
    (tmp_dir / "alpha" / "sub").mkdir()
    settings = WebSettings(
        enabled=True, host="127.0.0.1", port=0, jwt_secret="x" * 32,
        telegram_bot_username="t",
    )
    server = WebServer(
        settings=settings,
        allowed_user_ids=[100],
        bot_username="t",
        session_manager=sm,
        event_bus=bus,
        bot_token="12345:abc",
        jwt_secret="x" * 32,
        project_paths=[tmp_dir / "alpha"],
    )
    try:
        yield server, sm
    finally:
        sm.close_sync()
        sm._engine.sync_engine.dispose()


async def _login(client, u, p):
    r = await client.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text


def _full_user(sm, project: Path) -> None:
    uid = sm.create_local_user(
        username="rw", password_hash=hash_password("pw123456"), is_admin=False
    )
    sm.set_project_access(uid, str(project), "full")


async def test_upload_requires_auth(setup):
    server, _sm = setup
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/api/files/upload",
            params={"project_path": str(server.project_paths[0]), "dir": ""},
            files=[("files", ("a.txt", b"x", "text/plain"))],
        )
    assert r.status_code == 401, r.text


async def test_readonly_user_cannot_upload(setup):
    server, sm = setup
    uid = sm.create_local_user(
        username="ro", password_hash=hash_password("pw123456"), is_admin=False
    )
    sm.set_project_access(uid, str(server.project_paths[0]), "readonly")
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _login(client, "ro", "pw123456")
        r = await client.post(
            "/api/files/upload",
            params={"project_path": str(server.project_paths[0]), "dir": ""},
            files=[("files", ("a.txt", b"x", "text/plain"))],
        )
    assert r.status_code == 403, r.text
    assert not (server.project_paths[0] / "a.txt").exists()


async def test_upload_rejects_dir_traversal(setup):
    server, sm = setup
    _full_user(sm, server.project_paths[0])
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _login(client, "rw", "pw123456")
        r = await client.post(
            "/api/files/upload",
            params={"project_path": str(server.project_paths[0]), "dir": "../"},
            files=[("files", ("x.txt", b"x", "text/plain"))],
        )
    assert r.status_code == 400, r.text
    assert not (server.project_paths[0].parent / "x.txt").exists()


async def test_full_user_uploads_multiple_files(setup):
    server, sm = setup
    root = server.project_paths[0]
    _full_user(sm, root)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _login(client, "rw", "pw123456")
        r = await client.post(
            "/api/files/upload",
            params={"project_path": str(root), "dir": "sub"},
            files=[
                ("files", ("a.txt", b"aaa", "text/plain")),
                ("files", ("b.txt", b"bbb", "text/plain")),
            ],
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [e["rel"] for e in body["uploaded"]] == ["sub/a.txt", "sub/b.txt"]
    assert body["errors"] == []
    assert (root / "sub" / "a.txt").read_bytes() == b"aaa"
    assert (root / "sub" / "b.txt").read_bytes() == b"bbb"


async def test_upload_partial_success_on_conflict(setup):
    server, sm = setup
    root = server.project_paths[0]
    (root / "exists.txt").write_text("old", encoding="utf-8")
    _full_user(sm, root)
    transport = ASGITransport(app=server.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _login(client, "rw", "pw123456")
        r = await client.post(
            "/api/files/upload",
            params={"project_path": str(root), "dir": ""},
            files=[
                ("files", ("exists.txt", b"new", "text/plain")),
                ("files", ("fresh.txt", b"ok", "text/plain")),
            ],
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert [e["rel"] for e in body["uploaded"]] == ["fresh.txt"]
    assert body["errors"][0]["name"] == "exists.txt"
    assert "already exists" in body["errors"][0]["error"]
    assert (root / "exists.txt").read_text(encoding="utf-8") == "old"
    assert (root / "fresh.txt").read_bytes() == b"ok"
