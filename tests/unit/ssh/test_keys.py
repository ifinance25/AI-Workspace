"""SSH private key parse + fingerprint."""
from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.ssh.keys import InvalidSshKeyError, fingerprint_private_key, load_private_key


def _make_openssh_key() -> str:
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def test_fingerprint_stable_for_same_key():
    pem = _make_openssh_key()
    fp1 = fingerprint_private_key(pem)
    fp2 = fingerprint_private_key(pem)
    assert fp1 == fp2
    assert fp1.startswith("SHA256:")
    assert len(fp1) > 20


def test_empty_key_rejected():
    with pytest.raises(InvalidSshKeyError, match="пустой"):
        load_private_key("   ")


def test_garbage_rejected():
    with pytest.raises(InvalidSshKeyError, match="не SSH-ключ"):
        load_private_key("not-a-key")


def test_malformed_pem_rejected():
    with pytest.raises(InvalidSshKeyError):
        load_private_key(
            "-----BEGIN OPENSSH PRIVATE KEY-----\nnot-valid-base64\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
