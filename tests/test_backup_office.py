"""Ночная копия сервера валидации: база и файлы, проверка целостности, срок хранения."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import tarfile
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_office.sh"


def _run(data: Path, backup: Path, **extra: str) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ["PATH"], "DATA_DIR": str(data), "BACKUP_DIR": str(backup), **extra}
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )


@pytest.fixture
def data(tmp_path):
    folder = tmp_path / "data"
    (folder / "office_validation" / "p1" / "r1" / "findings").mkdir(parents=True)
    (folder / "office_validation" / "p1" / "r1" / "findings" / "R4-001.md").write_text("файл")
    conn = sqlite3.connect(folder / "sessions.db")
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('решение')")
    conn.commit()
    conn.close()
    return folder


def test_backup_contains_database_and_files(data, tmp_path):
    backup = tmp_path / "backups"
    result = _run(data, backup)
    assert result.returncode == 0, result.stderr
    archives = list(backup.glob("validation-*.tar.gz"))
    assert len(archives) == 1
    assert oct(archives[0].stat().st_mode & 0o777) == "0o600"
    with tarfile.open(archives[0]) as tar:
        assert sorted(tar.getnames()) == ["office_validation.tar", "sessions.db"]
        tar.extractall(tmp_path / "out", filter="data")
    restored = sqlite3.connect(tmp_path / "out" / "sessions.db")
    assert restored.execute("SELECT v FROM t").fetchone() == ("решение",)
    with tarfile.open(tmp_path / "out" / "office_validation.tar") as inner:
        assert "office_validation/p1/r1/findings/R4-001.md" in inner.getnames()
    assert not list(backup.glob(".tmp.*"))


def test_old_backups_are_removed(data, tmp_path):
    backup = tmp_path / "backups"
    backup.mkdir()
    old = backup / "validation-20200101T000000Z.tar.gz"
    old.write_bytes(b"x")
    long_ago = time.time() - 40 * 86400
    os.utime(old, (long_ago, long_ago))
    assert _run(data, backup, KEEP_DAYS="14").returncode == 0
    assert not old.exists()
    assert len(list(backup.glob("validation-*.tar.gz"))) == 1


def test_missing_database_fails(tmp_path):
    result = _run(tmp_path / "empty", tmp_path / "backups")
    assert result.returncode == 1 and "Нет базы" in result.stderr


def test_bad_keep_days_fails(data, tmp_path):
    result = _run(data, tmp_path / "backups", KEEP_DAYS="abc")
    assert result.returncode == 1


def test_corrupt_database_fails_without_archive(data, tmp_path):
    (data / "sessions.db").write_bytes(b"not a sqlite file" * 100)
    backup = tmp_path / "backups"
    result = _run(data, backup)
    assert result.returncode != 0
    assert not list(backup.glob("validation-*.tar.gz"))
