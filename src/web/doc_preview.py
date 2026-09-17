"""Просмотр старого Word (.doc): RTF и OLE Word 97-2003 → безопасный HTML.

Внешние конвертеры (textutil / LibreOffice) необязательны: без них остаётся
чистый Python. HTML режем до безопасных тегов; фронт ещё кладёт его в
sandbox-iframe без скриптов.
"""
from __future__ import annotations

import html
import re
import shutil
import struct
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path

MAX_DOC_PREVIEW_BYTES = 12 * 1024 * 1024
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_MAGIC = b"PK\x03\x04"
_EXT_ALIASES = {"док": "doc"}

_CPG = {
    1250: "cp1250",
    1251: "cp1251",
    1252: "cp1252",
    1253: "cp1253",
    1254: "cp1254",
    866: "cp866",
    10007: "mac_cyrillic",
    65001: "utf-8",
}

# RTF-группы, текст из которых в превью не нужен (шрифты, картинки, поля).
_RTF_SKIP = frozenset({
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "object",
    "header", "headerl", "headerr", "headerf",
    "footer", "footerl", "footerr", "footerf",
    "footnote", "annotation", "field", "xe", "tc",
    "listtable", "listoverridetable", "rsidtbl", "generator",
    "xmlnstbl", "mmath", "shpinst", "datastore", "themedata",
    "colorschememapping", "latentstyles", "filetbl",
})

_RTF_TOKEN = re.compile(
    r"\\([a-z]{1,32})(-?\d{1,10})?[ ]?|\\'([0-9a-f]{2})|\\([^a-z])|([{}])|[\r\n]+|(.)",
    re.I | re.S,
)

_ALLOWED_TAGS = frozenset({
    "p", "br", "b", "strong", "i", "em", "u", "table", "thead", "tbody",
    "tr", "td", "th", "span", "div", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "pre", "blockquote", "hr", "sup", "sub",
})
_SKIP_TAGS = frozenset({
    "script", "style", "iframe", "object", "embed", "link", "meta",
    "base", "head", "title",
})


class DocPreviewError(Exception):
    """Понятная ошибка превью: status + текст для UI."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.status = status


def normalized_file_ext(rel: str) -> str:
    """Последнее расширение в нижнем регистре; кириллическое «док» → doc."""
    base = rel.replace("\\", "/").rsplit("/", 1)[-1]
    _, sep, ext = base.rpartition(".")
    if not sep or not ext or ext == base:
        return ""
    ext = ext.casefold()
    return _EXT_ALIASES.get(ext, ext)


def is_legacy_doc_name(rel: str) -> bool:
    return normalized_file_ext(rel) == "doc"


def convert_doc_file(path: Path, *, use_external: bool = True) -> str:
    size = path.stat().st_size
    if size > MAX_DOC_PREVIEW_BYTES:
        raise DocPreviewError("Документ слишком большой для просмотра", 413)
    data = path.read_bytes()
    return convert_doc_bytes(data, src_path=path if use_external else None)


def convert_doc_bytes(data: bytes, *, src_path: Path | None = None) -> str:
    if src_path is not None:
        html_out = _try_textutil(src_path) or _try_soffice(src_path)
        if html_out:
            return html_out
    stripped = data.lstrip()
    if stripped.startswith(b"{\\rtf"):
        return sanitize_html(rtf_to_html(data))
    if data.startswith(_OLE_MAGIC):
        return sanitize_html(_text_to_html(_ole_to_text(data)))
    if data.startswith(_ZIP_MAGIC):
        raise DocPreviewError(
            "Это похоже на DOCX. Переименуйте файл в .docx и откройте снова."
        )
    raise DocPreviewError(
        "Не удалось открыть файл .doc. Скачайте его и откройте в Word."
    )


def _try_textutil(path: Path) -> str | None:
    exe = shutil.which("textutil")
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "preview.html"
        try:
            subprocess.run(
                [exe, "-convert", "html", "-output", str(out), str(path)],
                check=True,
                timeout=20,
                capture_output=True,
            )
        except (subprocess.SubprocessError, OSError, TimeoutError):
            return None
        if not out.is_file():
            return None
        raw = out.read_text(encoding="utf-8", errors="replace")
        cleaned = sanitize_html(raw)
        return cleaned if cleaned.strip() else None


def _try_soffice(path: Path) -> str | None:
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        return None
    with tempfile.TemporaryDirectory() as td:
        try:
            subprocess.run(
                [
                    exe, "--headless", "--nologo", "--nofirststartwizard",
                    "--norestore", "--convert-to", "html:HTML",
                    "--outdir", td, str(path),
                ],
                check=True,
                timeout=45,
                capture_output=True,
            )
        except (subprocess.SubprocessError, OSError, TimeoutError):
            return None
        htmls = list(Path(td).glob("*.html"))
        if not htmls:
            return None
        raw = htmls[0].read_text(encoding="utf-8", errors="replace")
        cleaned = sanitize_html(raw)
        return cleaned if cleaned.strip() else None


def _text_to_html(text: str) -> str:
    parts: list[str] = []
    for para in re.split(r"\r\n|\r|\n", text):
        chunk = para.strip()
        if chunk:
            parts.append(f"<p>{html.escape(chunk)}</p>")
    return "".join(parts) or "<p><em>Пустой документ</em></p>"


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip += 1
            return
        if self._skip or tag in {"html", "body"}:
            return
        if tag in {"br", "hr"}:
            self._out.append(f"<{tag}>")
            return
        if tag not in _ALLOWED_TAGS:
            return
        extra: list[str] = []
        for key, val in attrs:
            key = key.lower()
            if key in {"colspan", "rowspan"} and val and str(val).isdigit():
                extra.append(f'{key}="{val}"')
        if extra:
            self._out.append(f"<{tag} {' '.join(extra)}>")
        else:
            self._out.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            if self._skip:
                self._skip -= 1
            return
        if self._skip or tag in {"html", "body", "br", "hr"}:
            return
        if tag in _ALLOWED_TAGS:
            self._out.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._skip and data:
            self._out.append(html.escape(data, quote=False))

    def result(self) -> str:
        return "".join(self._out)


def sanitize_html(raw: str) -> str:
    parser = _Sanitizer()
    parser.feed(raw)
    parser.close()
    out = parser.result().strip()
    return out


def rtf_to_html(data: bytes) -> str:
    """RTF (часто .doc с кириллицей и ansicpg1251) → простой HTML."""
    try:
        src = data.decode("latin-1")
    except UnicodeDecodeError:
        src = data.decode("utf-8", errors="replace")

    codec = "cp1252"
    skip = 0
    ignorable = False
    uc = 1
    skip_uc = 0
    bold = italic = False
    in_table = False
    cell_open = False
    out: list[str] = ["<p>"]
    stack: list[tuple[bool, int, bool, bool, int]] = []

    def close_inline() -> None:
        nonlocal bold, italic
        if italic:
            out.append("</em>")
            italic = False
        if bold:
            out.append("</strong>")
            bold = False

    def ensure_cell() -> None:
        nonlocal in_table, cell_open
        if not in_table:
            close_inline()
            if out and out[-1] == "<p>":
                out.pop()
            elif out and not out[-1].endswith("</p>"):
                out.append("</p>")
            out.append("<table><tr>")
            in_table = True
        if not cell_open:
            out.append("<td>")
            cell_open = True

    def end_cell() -> None:
        nonlocal cell_open
        ensure_cell()
        close_inline()
        out.append("</td>")
        cell_open = False

    def end_row() -> None:
        nonlocal cell_open
        if cell_open:
            end_cell()
        elif in_table:
            pass
        out.append("</tr><tr>")

    def end_table() -> None:
        nonlocal in_table, cell_open
        if not in_table:
            return
        close_inline()
        if cell_open:
            out.append("</td>")
            cell_open = False
        if out and out[-1] == "<tr>":
            out.pop()
        elif out and out[-1].endswith("<tr>"):
            out[-1] = out[-1][:-4]
        out.append("</table><p>")
        in_table = False

    def emit(text: str) -> None:
        if skip:
            return
        if in_table:
            ensure_cell()
        out.append(html.escape(text, quote=False))

    def set_bold(on: bool) -> None:
        nonlocal bold
        if skip:
            return
        if on and not bold:
            if in_table:
                ensure_cell()
            out.append("<strong>")
            bold = True
        elif not on and bold:
            out.append("</strong>")
            bold = False

    def set_italic(on: bool) -> None:
        nonlocal italic
        if skip:
            return
        if on and not italic:
            if in_table:
                ensure_cell()
            out.append("<em>")
            italic = True
        elif not on and italic:
            out.append("</em>")
            italic = False

    for match in _RTF_TOKEN.finditer(src):
        word, arg, hexbyte, esc, brace, char = match.groups()
        if skip_uc and (hexbyte or char or (word and word.lower() != "u")):
            skip_uc -= 1
            continue
        if brace == "{":
            stack.append((ignorable, skip, bold, italic, uc))
            if ignorable:
                skip += 1
            ignorable = False
            continue
        if brace == "}":
            if not stack:
                continue
            was_skip = skip
            ignorable, skip, want_b, want_i, uc = stack.pop()
            if was_skip and skip == 0:
                continue
            if not skip:
                set_bold(want_b)
                set_italic(want_i)
            continue
        if hexbyte is not None:
            if skip:
                continue
            try:
                emit(bytes([int(hexbyte, 16)]).decode(codec, errors="replace"))
            except LookupError:
                emit(chr(int(hexbyte, 16)))
            continue
        if esc is not None:
            if skip:
                continue
            if esc in "{}\\":
                emit(esc)
            elif esc == "~":
                emit("\u00a0")
            elif esc == "_":
                emit("-")
            continue
        if word:
            name = word.lower()
            n = int(arg) if arg is not None else None
            if name == "*":
                ignorable = True
                continue
            if name == "ansicpg" and n is not None:
                codec = _CPG.get(n, codec)
                continue
            if name == "uc" and n is not None:
                uc = max(0, n)
                continue
            if name == "u" and n is not None:
                if not skip:
                    code = n + 65536 if n < 0 else n
                    try:
                        emit(chr(code))
                    except ValueError:
                        pass
                skip_uc = uc
                continue
            if name in _RTF_SKIP:
                skip += 1
                ignorable = False
                continue
            if skip:
                continue
            if name == "par":
                close_inline()
                if in_table:
                    emit("\n")
                else:
                    out.append("</p><p>")
            elif name == "line":
                out.append("<br>")
            elif name in {"tab", "emspace", "enspace"}:
                emit("\t")
            elif name == "b":
                set_bold(n != 0)
            elif name == "i":
                set_italic(n != 0)
            elif name in {"trowd", "intbl"}:
                ensure_cell()
            elif name == "cell":
                end_cell()
            elif name == "row":
                end_row()
            elif name == "pard" and in_table and n is None:
                # \pard без \intbl часто закрывает таблицу.
                pass
            continue
        if char is not None and not skip:
            emit(char)

    close_inline()
    end_table()
    if out and out[-1] == "<p>":
        out.pop()
    else:
        out.append("</p>")
    html_out = "".join(out)
    html_out = re.sub(r"<p>\s*</p>", "", html_out)
    html_out = re.sub(r"<tr>\s*</tr>", "", html_out)
    html_out = re.sub(r"<td>\s*</td>", "<td></td>", html_out)
    return html_out.strip() or "<p><em>Пустой документ</em></p>"


def _ole_to_text(data: bytes) -> str:
    try:
        import olefile
    except ImportError as exc:
        raise DocPreviewError(
            "Не удалось открыть Word 97-2003: на сервере нет пакета olefile."
        ) from exc
    try:
        ole = olefile.OleFileIO(data)
    except Exception as exc:
        raise DocPreviewError("Не удалось разобрать документ Word 97-2003.") from exc
    try:
        if not ole.exists("WordDocument"):
            raise DocPreviewError("Не удалось разобрать документ Word 97-2003.")
        word = ole.openstream("WordDocument").read()
        if len(word) < 0x1AA:
            raise DocPreviewError("Не удалось разобрать документ Word 97-2003.")
        magic = struct.unpack_from("<H", word, 0)[0]
        if magic != 0xA5EC:
            raise DocPreviewError("Не удалось разобрать документ Word 97-2003.")
        flags = struct.unpack_from("<H", word, 0x0A)[0]
        if flags & 0x0100:
            raise DocPreviewError("Документ защищён паролем, просмотр недоступен.")
        table_name = "1Table" if flags & 0x0200 else "0Table"
        if not ole.exists(table_name):
            raise DocPreviewError("Не удалось разобрать документ Word 97-2003.")
        table = ole.openstream(table_name).read()
        lid = struct.unpack_from("<H", word, 0x06)[0]
        ansi = "cp1251" if lid == 0x0419 else "cp1252"
        ccp_text = struct.unpack_from("<I", word, 76)[0]
        fc_clx = struct.unpack_from("<I", word, 0x1A2)[0]
        lcb_clx = struct.unpack_from("<I", word, 0x1A6)[0]
        if lcb_clx <= 0 or fc_clx + lcb_clx > len(table):
            raise DocPreviewError("Не удалось разобрать документ Word 97-2003.")
        clx = table[fc_clx : fc_clx + lcb_clx]
        piece = _clx_piece_table(clx)
        text = _read_pieces(word, piece, ansi)
        if ccp_text > 0:
            text = text[:ccp_text]
        text = text.replace("\x07", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
        text = text.replace("\r", "\n")
        text = "".join(ch for ch in text if ch == "\n" or ch >= " ")
        if not text.strip():
            raise DocPreviewError("Не удалось извлечь текст из документа .doc.")
        return text
    finally:
        try:
            ole.close()
        except Exception:
            pass


def _clx_piece_table(clx: bytes) -> bytes:
    offset = 0
    while offset < len(clx):
        kind = clx[offset]
        if kind == 1:
            if offset + 3 > len(clx):
                break
            cb = struct.unpack_from("<H", clx, offset + 1)[0]
            offset += 3 + cb
        elif kind == 2:
            if offset + 5 > len(clx):
                break
            lcb = struct.unpack_from("<I", clx, offset + 1)[0]
            start = offset + 5
            return clx[start : start + lcb]
        else:
            break
    raise DocPreviewError("Не удалось разобрать документ Word 97-2003.")


def _read_pieces(word: bytes, piece: bytes, ansi: str) -> str:
    if len(piece) < 16:
        raise DocPreviewError("Не удалось разобрать документ Word 97-2003.")
    n = (len(piece) - 4) // 12
    if n <= 0:
        raise DocPreviewError("Не удалось разобрать документ Word 97-2003.")
    cps = [struct.unpack_from("<I", piece, i * 4)[0] for i in range(n + 1)]
    pcd_off = (n + 1) * 4
    chunks: list[str] = []
    for i in range(n):
        fc_val = struct.unpack_from("<I", piece, pcd_off + i * 8 + 2)[0]
        compressed = bool(fc_val & 0x40000000)
        fc = fc_val & 0x3FFFFFFF
        count = cps[i + 1] - cps[i]
        if count <= 0:
            continue
        if compressed:
            pos = fc // 2
            raw = word[pos : pos + count]
            chunks.append(raw.decode(ansi, errors="replace"))
        else:
            raw = word[fc : fc + count * 2]
            chunks.append(raw.decode("utf-16le", errors="replace"))
    return "".join(chunks)
