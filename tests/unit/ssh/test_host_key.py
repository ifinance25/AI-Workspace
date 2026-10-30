"""У43-06: терминал SSH проверяет ключ сервера.

Настоящий сервер asyncssh на петлевом адресе. Первое подключение запоминает ключ
сервера, второе с тем же ключом проходит, подключение к серверу с другим ключом
получает отказ до входа. Пароли и сеть наружу не нужны.
"""
from __future__ import annotations

import dataclasses

import asyncssh
import pytest

from src.connections.crypto import SecretBox
from src.ssh.session import (
    HOST_KEY_CHANGED_MESSAGE,
    SshConnectError,
    host_key_fingerprint,
    known_hosts_for,
    open_ssh_shell,
    public_ssh_error,
)
from src.ssh.store import SshProfile, SshStore


class _NoAuthServer(asyncssh.SSHServer):
    def begin_auth(self, username: str) -> bool:
        return False  # вход без проверки: тест про ключ сервера, не про вход


async def _handle(process: asyncssh.SSHServerProcess) -> None:
    process.exit(0)


async def _listen(host_key: asyncssh.SSHKey) -> asyncssh.SSHAcceptor:
    return await asyncssh.listen(
        "127.0.0.1",
        0,
        server_host_keys=[host_key],
        server_factory=_NoAuthServer,
        process_factory=_handle,
    )


def _profile(port: int, host_key: str | None = None) -> SshProfile:
    client_key = asyncssh.generate_private_key("ssh-ed25519")
    return SshProfile(
        host="127.0.0.1",
        port=port,
        username="tester",
        private_key=client_key.export_private_key("openssh").decode(),
        passphrase=None,
        fingerprint="SHA256:test",
        host_key=host_key,
    )


def _public(key: asyncssh.SSHKey) -> str:
    return key.export_public_key("openssh").decode().strip()


async def _close(conn, process) -> None:
    process.close()
    conn.close()
    await conn.wait_closed()


def test_known_hosts_none_until_first_connect() -> None:
    assert known_hosts_for(_profile(22)) is None
    key = asyncssh.generate_private_key("ssh-ed25519")
    trusted, cas, revoked = known_hosts_for(_profile(22, _public(key)))
    assert len(trusted) == 1 and cas == [] and revoked == []
    assert host_key_fingerprint(_public(key)).startswith("SHA256:")
    assert host_key_fingerprint(None) is None
    assert host_key_fingerprint("мусор") is None


def test_host_key_error_message_has_no_secrets() -> None:
    assert public_ssh_error(asyncssh.HostKeyNotVerifiable("x")) == HOST_KEY_CHANGED_MESSAGE
    assert "SHA256" not in HOST_KEY_CHANGED_MESSAGE


def test_store_keeps_host_key_in_encrypted_blob(tmp_path) -> None:
    from cryptography.fernet import Fernet

    store = SshStore(tmp_path / "ssh.db", SecretBox(Fernet.generate_key().decode()))
    store.save(7, _profile(22))
    assert store.get(7).host_key is None
    assert store.remember_host_key(7, "ssh-ed25519 AAAAtest")
    assert store.get(7).host_key == "ssh-ed25519 AAAAtest"
    assert not store.remember_host_key(8, "ssh-ed25519 AAAAtest")
    store.close()


async def test_first_connect_remembers_then_verifies_host_key() -> None:
    server_key = asyncssh.generate_private_key("ssh-ed25519")
    acceptor = await _listen(server_key)
    try:
        port = acceptor.get_port()
        seen: list[str] = []
        conn, process = await open_ssh_shell(_profile(port), on_host_key=seen.append)
        await _close(conn, process)
        assert seen == [_public(server_key)]

        trusted = dataclasses.replace(_profile(port), host_key=seen[0])
        conn, process = await open_ssh_shell(trusted, on_host_key=seen.append)
        await _close(conn, process)
        assert len(seen) == 1  # ключ уже известен: второй раз не запоминаем
    finally:
        acceptor.close()
        await acceptor.wait_closed()


async def test_changed_host_key_is_refused_before_login() -> None:
    server_key = asyncssh.generate_private_key("ssh-ed25519")
    other_key = asyncssh.generate_private_key("ssh-ed25519")
    acceptor = await _listen(server_key)
    try:
        port = acceptor.get_port()
        stale = _profile(port, host_key=_public(other_key))
        with pytest.raises(SshConnectError) as refused:
            await open_ssh_shell(stale)
        assert str(refused.value) == HOST_KEY_CHANGED_MESSAGE
    finally:
        acceptor.close()
        await acceptor.wait_closed()
