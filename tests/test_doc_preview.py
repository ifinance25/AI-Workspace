"""Превью старого .doc: расширение, RTF, отказ на мусоре, XSS."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.web.doc_preview import (
    DocPreviewError,
    convert_doc_bytes,
    convert_doc_file,
    is_legacy_doc_name,
    rtf_to_html,
    sanitize_html,
)


def _rtf_cp1251(text: str, *, extra: str = "") -> bytes:
    parts = [r"{\rtf1\ansi\ansicpg1251\pard " + extra]
    for ch in text:
        code = ord(ch)
        if ch == "\\":
            parts.append("\\\\")
        elif ch in "{}":
            parts.append("\\" + ch)
        elif code < 128:
            parts.append(ch)
        else:
            parts.append("".join(f"\\'{b:02x}" for b in ch.encode("cp1251")))
    parts.append(r"\par}")
    return "".join(parts).encode("ascii")


def test_legacy_doc_ext_case_and_cyrillic():
    assert is_legacy_doc_name("note.doc")
    assert is_legacy_doc_name("note.DOC")
    assert is_legacy_doc_name("docs/документ.Док")
    assert not is_legacy_doc_name("note.docx")
    assert not is_legacy_doc_name("note.txt")


def test_rtf_doc_extracts_cyrillic_and_escapes_html():
    data = _rtf_cp1251("Привет <script>alert(1)</script>")
    html = convert_doc_bytes(data)
    assert "Привет" in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_rtf_bold_and_table():
    raw = (
        r"{\rtf1\ansi\deff0 {\b Bold}\par "
        r"\trowd\cellx1000 A\cell B\cell\row}"
    ).encode("ascii")
    html = rtf_to_html(raw)
    assert "<strong>" in html
    assert "Bold" in html
    assert "<table>" in html
    assert "<td>" in html
    assert "A" in html and "B" in html


def test_garbage_bytes_raise_clear_error():
    with pytest.raises(DocPreviewError) as exc:
        convert_doc_bytes(b"\x00\x01not-a-doc")
    assert exc.value.status == 422
    assert "Скачайте" in exc.value.message


def test_zip_misnamed_as_doc_asks_rename():
    with pytest.raises(DocPreviewError) as exc:
        convert_doc_bytes(b"PK\x03\x04dummy-docx")
    assert "DOCX" in exc.value.message


def test_sanitize_strips_script():
    html = sanitize_html('<p>ok</p><script>alert(1)</script><p onclick="x">x</p>')
    assert "<script>" not in html
    assert "alert" not in html
    assert "onclick" not in html
    assert "ok" in html


def test_convert_file_too_large(tmp_path: Path, monkeypatch):
    path = tmp_path / "huge.doc"
    path.write_bytes(_rtf_cp1251("x"))
    monkeypatch.setattr("src.web.doc_preview.MAX_DOC_PREVIEW_BYTES", 1)
    with pytest.raises(DocPreviewError) as exc:
        convert_doc_file(path, use_external=False)
    assert exc.value.status == 413
