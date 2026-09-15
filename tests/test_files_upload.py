"""Запись файлов из локального диска в каталог проекта (анти-traversal)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.web.routes_files import (
    Conflict,
    PathError,
    save_uploaded_file,
    safe_upload_filename,
)


def test_safe_upload_filename_strips_directories():
    assert safe_upload_filename("../../../etc/passwd") == "passwd"
    assert safe_upload_filename("a\\b\\c.txt") == "c.txt"
    assert safe_upload_filename("отчёт.pdf") == "отчёт.pdf"


def test_safe_upload_filename_rejects_dots():
    with pytest.raises(PathError):
        safe_upload_filename("..")
    with pytest.raises(PathError):
        safe_upload_filename(".")
    with pytest.raises(PathError):
        safe_upload_filename("")


def test_save_uploaded_file_writes_into_subdir(tmp_path: Path):
    dest_dir = tmp_path / "docs"
    dest_dir.mkdir()
    out = save_uploaded_file(tmp_path, "docs", "note.txt", b"hello")
    assert out["rel"] == "docs/note.txt"
    assert (tmp_path / "docs" / "note.txt").read_bytes() == b"hello"
    assert out["size_bytes"] == 5


def test_save_uploaded_file_strips_traversal_in_name(tmp_path: Path):
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("nope", encoding="utf-8")
    out = save_uploaded_file(tmp_path, "", "../secret.txt", b"safe")
    assert out["rel"] == "secret.txt"
    assert (tmp_path / "secret.txt").read_bytes() == b"safe"
    assert secret.read_text(encoding="utf-8") == "nope"


def test_save_uploaded_file_rejects_dir_traversal(tmp_path: Path):
    outside = tmp_path.parent / "outside"
    outside.mkdir()
    with pytest.raises(PathError):
        save_uploaded_file(tmp_path, "../outside", "x.txt", b"x")
    assert not (outside / "x.txt").exists()


def test_save_uploaded_file_conflict_does_not_overwrite(tmp_path: Path):
    (tmp_path / "a.txt").write_text("old", encoding="utf-8")
    with pytest.raises(Conflict):
        save_uploaded_file(tmp_path, "", "a.txt", b"new")
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "old"
