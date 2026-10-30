"""У43-05: ключ Redmine не уходит на редирект и не ходит по http в сеть.

Подделка Redmine на петлевом адресе отвечает 302 на второй сервер: второй
сервер не должен увидеть ни одного запроса. Адрес с http на не-петлевой хост
отвергается и клиентом, и формой админа.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from cryptography.fernet import Fernet

from src.office import redmine_mirror
from src.office.redmine_mirror._http import HttpRedmine
from src.office.storage import OfficeStore


class _Recorder(HTTPServer):
    def __init__(self, *args, redirect_to: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.redirect_to = redirect_to


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: D401 - тише в тестах
        return

    def do_GET(self) -> None:  # noqa: N802
        server: _Recorder = self.server  # type: ignore[assignment]
        server.requests.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
        if server.redirect_to:
            self.send_response(302)
            self.send_header("Location", server.redirect_to + self.path)
            self.end_headers()
            return
        body = b'{"issue": {"id": 1, "subject": "x"}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def two_servers():
    target = _Recorder(("127.0.0.1", 0), _Handler)
    target_url = f"http://127.0.0.1:{target.server_port}"
    source = _Recorder(("127.0.0.1", 0), _Handler, redirect_to=target_url)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (target, source)]
    for t in threads:
        t.start()
    try:
        yield source, target
    finally:
        for s in (source, target):
            s.shutdown()
            s.server_close()


def test_key_does_not_follow_redirect(two_servers) -> None:
    source, target = two_servers
    client = HttpRedmine(f"http://127.0.0.1:{source.server_port}", "secret-key-1")
    with pytest.raises(redmine_mirror.RedmineUnavailableError) as failed:
        client.get_issue(1)
    assert "перенаправляет" in str(failed.value)
    assert source.requests and source.requests[0][1]["x-redmine-api-key"] == "secret-key-1"
    assert target.requests == []


def test_plain_http_to_remote_host_is_refused() -> None:
    with pytest.raises(redmine_mirror.MirrorError) as refused:
        HttpRedmine("http://redmine.example", "secret-key-1")
    assert refused.value.code == "bad_url"


def test_https_and_loopback_http_are_allowed() -> None:
    assert redmine_mirror.url_allowed("https://redmine.example")
    assert redmine_mirror.url_allowed("http://127.0.0.1:3000")
    assert not redmine_mirror.url_allowed("http://redmine.example")
    assert not redmine_mirror.url_allowed("https://user:pw@redmine.example")
    assert not redmine_mirror.url_allowed("ftp://redmine.example")


def test_admin_form_refuses_plain_http(tmp_path) -> None:
    store = OfficeStore(tmp_path / "office.db")
    cipher = redmine_mirror.cipher_from_key(Fernet.generate_key().decode())
    with pytest.raises(ValueError):
        redmine_mirror.save_account(
            store, cipher, base_url="http://redmine.example", redmine_project="hr", api_key="k"
        )
    saved = redmine_mirror.save_account(
        store, cipher, base_url="https://redmine.example/", redmine_project="hr", api_key="k"
    )
    assert saved["base_url"] == "https://redmine.example"
    store.close()
