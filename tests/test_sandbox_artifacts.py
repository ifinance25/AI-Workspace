"""Артефакты из песочницы Claude попадают в список и скачиваются."""
import shutil
from pathlib import Path

import pytest

from src.claude.sandbox_files import claude_sandbox_prefix, encode_claude_cwd
from src.web.routes_files import PathError, aggregate_artifacts, delete_entry
from src.web.routes_sessions import resolve_session_file


def _sandbox_file(project: Path, name: str) -> Path:
    session = claude_sandbox_prefix(project) / "59b12f3f-1502-45aa-95cd-120505dba90b"
    path = session / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("888", encoding="utf-8")
    return path


def test_encode_replaces_slash_and_non_ascii() -> None:
    encoded = encode_claude_cwd("/data/local-projects/Общий")
    assert encoded == "-data-local-projects------"


def test_aggregate_includes_sandbox_file_and_skips_other_project(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    inside = _sandbox_file(project, "scratchpad/test.txt")
    outside = _sandbox_file(other, "scratchpad/secret.txt")
    try:
        rows = [
            {"tool": "Write", "file_path": str(inside), "created_at": "2026-01-02"},
            {"tool": "Write", "file_path": str(outside), "created_at": "2026-01-03"},
            {"tool": "Write", "file_path": "/etc/passwd", "created_at": "2026-01-04"},
        ]
        out = aggregate_artifacts(project, rows, set())
        assert [a["display"] for a in out] == ["scratchpad/test.txt"]
        assert out[0]["exists"] is True
        assert out[0]["name"] == "test.txt"
    finally:
        shutil.rmtree(claude_sandbox_prefix(project), ignore_errors=True)
        shutil.rmtree(claude_sandbox_prefix(other), ignore_errors=True)


def test_download_and_delete_sandbox_file(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    inside = _sandbox_file(project, "scratchpad/test.txt")
    try:
        assert resolve_session_file(project, str(inside)) == inside.resolve()
        with pytest.raises(ValueError):
            resolve_session_file(project, str(claude_sandbox_prefix(project).parent / "escape.txt"))
        delete_entry(project, str(inside))
        assert not inside.exists()
    finally:
        shutil.rmtree(claude_sandbox_prefix(project), ignore_errors=True)


def test_sandbox_escape_is_not_an_artifact(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    prefix = claude_sandbox_prefix(project)
    try:
        with pytest.raises(PathError):
            delete_entry(project, str(prefix / ".." / "passwd"))
    finally:
        shutil.rmtree(prefix, ignore_errors=True)
