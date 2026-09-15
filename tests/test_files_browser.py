"""Браузер файлов: чтение/запись на диск, в том числе путь из JS-клиента.

Симптом: файл создаётся, а текст из редактора на диск не попадает. Браузер
парсит JSON-число ``mtime_ns`` как IEEE-754 double (~53 бита), теряет младшие
наносекунды и шлёт ``expected_mtime_ns``, который не совпадает с диском → 409
без записи. Python-json сохраняет int точно, поэтому тест явно эмулирует
округление JS.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.web.routes_files import Conflict, PathError, WriteIn, read_text_file, write_text_file

# Наносекунды, которые не представимы точно в JS Number (ULP около 2^60 = 256).
_NS = 1_757_952_000_123_456_789


def js_json_int(n: int) -> int:
    """JSON.parse числа в браузере: IEEE-754 double → целое."""
    return int(float(n))


def test_js_number_loses_mtime_ns_precision():
    rounded = js_json_int(_NS)
    assert rounded != _NS


def test_write_text_file_persists_when_mtime_matches(tmp_path: Path):
    (tmp_path / "a.txt").write_text("old", encoding="utf-8")
    mtime = (tmp_path / "a.txt").stat().st_mtime_ns
    out = write_text_file(tmp_path, "a.txt", "new", mtime)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "new"
    assert int(out["mtime_ns"]) == (tmp_path / "a.txt").stat().st_mtime_ns


def test_write_text_file_conflict_does_not_write(tmp_path: Path):
    (tmp_path / "a.txt").write_text("old", encoding="utf-8")
    with pytest.raises(Conflict):
        write_text_file(tmp_path, "a.txt", "new", expected_mtime_ns=1)
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "old"


def test_browser_json_mtime_roundtrip_saves_to_disk(tmp_path: Path):
    """Как вкладка «Файлы»: GET JSON → JSON.parse в JS → PUT expected_mtime_ns."""
    target = tmp_path / "note.txt"
    target.write_text("", encoding="utf-8")
    os.utime(target, ns=(_NS, _NS))
    on_disk = target.stat().st_mtime_ns
    assert js_json_int(on_disk) != on_disk

    wire = json.dumps(read_text_file(tmp_path, "note.txt"))
    payload = json.loads(wire)
    mtime = payload["mtime_ns"]
    assert isinstance(mtime, str)
    assert mtime == str(on_disk)

    write_text_file(tmp_path, "note.txt", "привет с панели", mtime)
    assert target.read_text(encoding="utf-8") == "привет с панели"


def test_js_rounded_mtime_number_still_conflicts(tmp_path: Path):
    """Округлённое JSON-число по-прежнему 409: проверку mtime не ослабляли."""
    target = tmp_path / "note.txt"
    target.write_text("old", encoding="utf-8")
    os.utime(target, ns=(_NS, _NS))
    with pytest.raises(Conflict):
        write_text_file(tmp_path, "note.txt", "new", js_json_int(target.stat().st_mtime_ns))
    assert target.read_text(encoding="utf-8") == "old"


def test_writein_parses_mtime_digit_string():
    body = WriteIn(content="x", expected_mtime_ns="1757952000123456789")
    assert body.expected_mtime_ns == 1757952000123456789


def test_write_rejects_invalid_mtime(tmp_path: Path):
    (tmp_path / "a.txt").write_text("old", encoding="utf-8")
    with pytest.raises(PathError):
        write_text_file(tmp_path, "a.txt", "new", "not-a-number")
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "old"
