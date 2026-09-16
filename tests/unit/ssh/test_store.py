"""SshStore encrypts the private key and returns it only via get()."""
from __future__ import annotations

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.connections.crypto import SecretBox
from src.ssh.keys import fingerprint_private_key
from src.ssh.store import SshProfile, SshStore


def _pem() -> str:
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def test_save_get_delete(tmp_path):
    box = SecretBox(Fernet.generate_key().decode())
    store = SshStore(tmp_path / "ssh.db", box)
    pem = _pem()
    fp = fingerprint_private_key(pem)
    store.save(
        7,
        SshProfile(
            host="example.com",
            port=22,
            username="ubuntu",
            private_key=pem,
            passphrase=None,
            fingerprint=fp,
        ),
    )
    got = store.get(7)
    assert got is not None
    assert got.host == "example.com"
    assert got.username == "ubuntu"
    assert got.private_key == pem
    assert got.fingerprint == fp
    assert store.get(8) is None
    assert store.delete(7) is True
    assert store.get(7) is None
    assert store.delete(7) is False
