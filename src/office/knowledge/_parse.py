"""Разбор входного файла в Markdown: ``.md`` и ``.txt`` как есть, ``.docx`` стандартной
библиотекой (zip + XML), без новой зависимости. Берутся заголовки, абзацы, пункты
списков и таблицы, не сырой XML."""

from __future__ import annotations

import io
import zipfile
from pathlib import PurePath
from xml.etree import ElementTree

from src.office.knowledge._versions import IngestError

ACCEPTED = (".md", ".txt", ".docx")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def to_markdown(filename: str, data: bytes) -> str:
    suffix = PurePath(filename).suffix.lower()
    if suffix not in ACCEPTED:
        raise IngestError(
            "unsupported",
            f"Файл «{filename}» не принят: загрузите бриф в формате .md, .txt или .docx.",
        )
    if suffix == ".docx":
        return _docx(data)
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IngestError(
        "unreadable", f"Файл «{filename}» не читается как текст: сохраните его в UTF-8."
    )


def _docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            root = ElementTree.fromstring(zf.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise IngestError(
            "unreadable", "Файл .docx повреждён или не является документом Word."
        ) from exc
    body = root.find(f"{_W}body")
    blocks: list[str] = []
    for node in [] if body is None else body:
        if node.tag == f"{_W}p":
            block = _paragraph(node)
        elif node.tag == f"{_W}tbl":
            block = _table(node)
        else:
            continue
        if block.strip():
            blocks.append(block)
    return "\n\n".join(blocks)


def _text(node) -> str:
    parts: list[str] = []
    for el in node.iter():
        if el.tag == f"{_W}t" and el.text:
            parts.append(el.text)
        elif el.tag == f"{_W}tab":
            parts.append("\t")
        elif el.tag in (f"{_W}br", f"{_W}cr"):
            parts.append("\n")
    return "".join(parts).strip()


def _paragraph(p) -> str:
    text = _text(p)
    if not text:
        return ""
    style_el = p.find(f"{_W}pPr/{_W}pStyle")
    style = (style_el.get(f"{_W}val") or "") if style_el is not None else ""
    if style == "Title":
        return f"# {text}"
    if style.startswith("Heading") and style[7:].isdigit():
        return f"{'#' * min(int(style[7:]), 6)} {text}"
    if p.find(f"{_W}pPr/{_W}numPr") is not None:
        return f"- {text}"
    return text


def _table(tbl) -> str:
    rows = [
        [_text(cell).replace("\n", " ").replace("|", "\\|") for cell in tr.findall(f"{_W}tc")]
        for tr in tbl.findall(f"{_W}tr")
    ]
    rows = [r for r in rows if r]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    lines = ["| " + " | ".join(r + [""] * (width - len(r))) + " |" for r in rows]
    lines.insert(1, "|" + " --- |" * width)
    return "\n".join(lines)
