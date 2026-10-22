"""Бриф проекта офиса: роутер ``/api/office/projects/{id}/brief``.

Текст и файл (.md, .txt, .docx) становятся версией Markdown; пустое и чужой тип
версию не создают; тот же текст подряд не плодит вторую версию; чужой проект 404.
"""

from __future__ import annotations

import io
import zipfile
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.office import tenancy
from src.web.passwords import hash_password
from src.web.server import WebServer

# Тестовый пароль локальных аккаунтов, не секрет.
_PASSWORD = "test-only-password"


@pytest.fixture
def server(tmp_path):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    settings = WebSettings(
        enabled=True,
        host="127.0.0.1",
        port=0,
        jwt_secret="x" * 32,
        telegram_bot_username="t",
    )
    srv = WebServer(
        settings=settings,
        allowed_user_ids=[],
        bot_username="t",
        session_manager=sm,
        event_bus=EventBus(),
        jwt_secret="x" * 32,
    )
    try:
        yield srv, sm
    finally:
        srv.office_store.close()
        sm.close_sync()
        sm._engine.sync_engine.dispose()


def _project(srv: WebServer, sm: SessionManager, username: str) -> int:
    uid = sm.create_local_user(
        username=username, password_hash=hash_password(_PASSWORD), is_admin=False
    )
    project = srv.office_store.create_project(name=f"Проект {username}", created_by=uid)
    tenancy.record_creator(srv.office_store, project["id"], uid)
    return project["id"]


@asynccontextmanager
async def _client(srv: WebServer, username: str):
    async with AsyncClient(transport=ASGITransport(app=srv.app), base_url="http://test") as client:
        r = await client.post("/api/auth/login", json={"username": username, "password": _PASSWORD})
        assert r.status_code == 200
        yield client


async def test_text_becomes_versions_and_old_version_is_kept(server) -> None:
    srv, sm = server
    pid = _project(srv, sm, "m1")
    async with _client(srv, "m1") as client:
        first = await client.post(
            f"/api/office/projects/{pid}/brief", json={"text": "# Сайт\n\nНужен лендинг."}
        )
        second = await client.post(
            f"/api/office/projects/{pid}/brief", json={"text": "# Сайт\n\nНужен лендинг и блог."}
        )
        listed = await client.get(f"/api/office/projects/{pid}/brief/versions")
        v1 = await client.get(f"/api/office/projects/{pid}/brief/versions/1")
    assert first.status_code == 201
    assert second.status_code == 201
    assert [v["number"] for v in listed.json()] == [1, 2]
    assert [v["source"] for v in listed.json()] == ["текст", "текст"]
    assert all(v["created_at"] for v in listed.json())
    assert v1.json()["markdown"] == "# Сайт\n\nНужен лендинг."


def _docx(paragraphs: list[tuple[str, str]]) -> bytes:
    """Минимальный .docx: (стиль, текст) на абзац; стиль ``Heading1`` или ``''``."""
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = ""
    for style, text in paragraphs:
        ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        body += f"<w:p>{ppr}<w:r><w:t>{text}</w:t></w:r></w:p>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", f"<w:document {ns}><w:body>{body}</w:body></w:document>")
    return buf.getvalue()


async def test_files_md_txt_docx_become_markdown(server) -> None:
    srv, sm = server
    pid = _project(srv, sm, "m1")
    url = f"/api/office/projects/{pid}/brief/file"
    docx = _docx([("Heading1", "Интернет-магазин"), ("", "Каталог и корзина.")])
    async with _client(srv, "m1") as client:
        md = await client.post(
            url, files={"file": ("brief.md", "# Бриф\n\nТекст.".encode(), "text/markdown")}
        )
        txt = await client.post(
            url, files={"file": ("brief.txt", "Просто текст.".encode(), "text/plain")}
        )
        word = await client.post(
            url, files={"file": ("brief.docx", docx, "application/octet-stream")}
        )
        listed = await client.get(f"/api/office/projects/{pid}/brief/versions")
        v3 = await client.get(f"/api/office/projects/{pid}/brief/versions/3")
    assert [md.status_code, txt.status_code, word.status_code] == [201, 201, 201]
    assert [v["source"] for v in listed.json()] == ["brief.md", "brief.txt", "brief.docx"]
    assert v3.json()["markdown"] == "# Интернет-магазин\n\nКаталог и корзина."


async def test_wrong_type_and_empty_file_create_no_version(server) -> None:
    srv, sm = server
    pid = _project(srv, sm, "m1")
    url = f"/api/office/projects/{pid}/brief/file"
    async with _client(srv, "m1") as client:
        pdf = await client.post(url, files={"file": ("brief.pdf", b"%PDF-1.4", "application/pdf")})
        empty = await client.post(url, files={"file": ("brief.md", b"  \n", "text/markdown")})
        listed = await client.get(f"/api/office/projects/{pid}/brief/versions")
    assert pdf.status_code == 415
    assert ".docx" in pdf.json()["detail"]
    assert empty.status_code == 400
    assert "Положите бриф" in empty.json()["detail"]
    assert listed.json() == []


async def test_file_larger_than_upload_limit_is_refused(server, monkeypatch) -> None:
    from src.web import routes_files

    monkeypatch.setattr(routes_files, "MAX_UPLOAD_BYTES", 10)
    srv, sm = server
    pid = _project(srv, sm, "m1")
    async with _client(srv, "m1") as client:
        r = await client.post(
            f"/api/office/projects/{pid}/brief/file",
            files={"file": ("brief.txt", ("x" * 11).encode(), "text/plain")},
        )
    assert r.status_code == 413


async def test_empty_text_creates_no_version(server) -> None:
    srv, sm = server
    pid = _project(srv, sm, "m1")
    async with _client(srv, "m1") as client:
        r = await client.post(f"/api/office/projects/{pid}/brief", json={"text": " \n\t"})
        listed = await client.get(f"/api/office/projects/{pid}/brief/versions")
    assert r.status_code == 400
    assert "Положите бриф" in r.json()["detail"]
    assert listed.json() == []


async def test_same_text_twice_keeps_one_version(server) -> None:
    srv, sm = server
    pid = _project(srv, sm, "m1")
    async with _client(srv, "m1") as client:
        first = await client.post(f"/api/office/projects/{pid}/brief", json={"text": "Нужен сайт."})
        again = await client.post(f"/api/office/projects/{pid}/brief", json={"text": "Нужен сайт."})
        listed = await client.get(f"/api/office/projects/{pid}/brief/versions")
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["version"]["number"] == 1
    assert len(listed.json()) == 1


async def test_foreign_project_brief_is_refused(server) -> None:
    srv, sm = server
    _project(srv, sm, "m1")
    foreign = _project(srv, sm, "m2")
    async with _client(srv, "m1") as client:
        post = await client.post(f"/api/office/projects/{foreign}/brief", json={"text": "Чужой."})
        listed = await client.get(f"/api/office/projects/{foreign}/brief/versions")
    assert post.status_code == 404
    assert listed.status_code == 404
