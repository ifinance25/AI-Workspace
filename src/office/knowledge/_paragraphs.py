"""Абзацы версии и карта абзацев между соседними версиями.

Идентификатор абзаца: отпечаток нормализованного текста (пробелы схлопнуты) и
порядковый номер среди одинаковых в этой версии, ``p-<sha1[:12]>-<n>``. Одинаковый
текст в двух версиях даёт одинаковый идентификатор. Абзацы версии хранятся JSON
в таблице ``office_paragraphs`` (писатель один: ``knowledge``); у версии без
записи они выводятся из Markdown тем же правилом.
"""

from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher

SIMILARITY = 0.6  # выше: «изменён», иначе «удалён» и «новый»

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS office_paragraphs ("
    "version_id INTEGER PRIMARY KEY REFERENCES office_document_versions(id) ON DELETE CASCADE, "
    "paragraphs TEXT NOT NULL)"
)
_HEADING = re.compile(r"^#{1,6}\s")


def split(markdown: str) -> list[str]:
    """Абзацы Markdown: блоки между пустыми строками; заголовок всегда отдельный абзац."""
    blocks: list[str] = []
    current: list[str] = []
    in_fence = False

    def flush() -> None:
        if current:
            blocks.append("\n".join(current).strip())
            current.clear()

    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and not line.strip():
            flush()
        elif not in_fence and _HEADING.match(line):
            flush()
            blocks.append(line.strip())
        else:
            current.append(line)
    flush()
    return [b for b in blocks if b]


def identify(markdown: str) -> list[dict]:
    """``[{"id", "text"}]`` по порядку абзацев."""
    seen: dict[str, int] = {}
    result = []
    for text in split(markdown):
        digest = hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:12]
        seen[digest] = seen.get(digest, 0) + 1
        result.append({"id": f"p-{digest}-{seen[digest]}", "text": text})
    return result


def _db(store):
    # OfficeStore не выставляет соединение публично; таблица knowledge живёт в той же базе
    # и под тем же замком, что версии.
    conn = store._connection()
    conn.execute(_SCHEMA)
    return conn


def save(store, version_id: int, markdown: str) -> list[dict]:
    paragraphs = identify(markdown)
    with store._lock:
        conn = _db(store)
        conn.execute(
            "INSERT OR REPLACE INTO office_paragraphs (version_id, paragraphs) VALUES (?, ?)",
            (version_id, json.dumps(paragraphs, ensure_ascii=False)),
        )
        conn.commit()
    return paragraphs


def load(store, version_id: int, markdown: str) -> list[dict]:
    with store._lock:
        row = (
            _db(store)
            .execute("SELECT paragraphs FROM office_paragraphs WHERE version_id = ?", (version_id,))
            .fetchone()
        )
    return json.loads(row[0]) if row is not None else identify(markdown)


def _lcs(a: list[str], b: list[str]) -> set[str]:
    """Идентификаторы, которые лежат в общей подпоследовательности: их порядок не менялся."""
    table = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) - 1, -1, -1):
        for j in range(len(b) - 1, -1, -1):
            table[i][j] = (
                table[i + 1][j + 1] + 1 if a[i] == b[j] else max(table[i + 1][j], table[i][j + 1])
            )
    kept, i, j = set(), 0, 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            kept.add(a[i])
            i, j = i + 1, j + 1
        elif table[i + 1][j] >= table[i][j + 1]:
            i += 1
        else:
            j += 1
    return kept


def build_map(old: list[dict], new: list[dict]) -> list[dict]:
    """Карта абзацев ``old`` -> ``new``.

    Элемент: ``{"status", "old_id", "new_id", "old_index", "new_index", "similarity"}``,
    статус ``same`` | ``moved`` | ``changed`` | ``removed`` | ``added``. Сначала точное
    совпадение идентификаторов (вне общего порядка: ``moved``), затем пары по схожести
    текста выше ``SIMILARITY``.
    """
    old_pos = {p["id"]: i for i, p in enumerate(old)}
    new_pos = {p["id"]: i for i, p in enumerate(new)}
    common = [p["id"] for p in old if p["id"] in new_pos]
    in_order = _lcs(common, [p["id"] for p in new if p["id"] in old_pos])
    entries = [
        {
            "status": "same" if pid in in_order else "moved",
            "old_id": pid,
            "new_id": pid,
            "old_index": old_pos[pid],
            "new_index": new_pos[pid],
            "similarity": 1.0,
        }
        for pid in common
    ]
    rest_old = [i for i, p in enumerate(old) if p["id"] not in new_pos]
    rest_new = [j for j, p in enumerate(new) if p["id"] not in old_pos]
    scored = sorted(
        (
            (SequenceMatcher(None, old[i]["text"], new[j]["text"]).ratio(), i, j)
            for i in rest_old
            for j in rest_new
        ),
        key=lambda t: (-t[0], t[1], t[2]),
    )
    paired_old: set[int] = set()
    paired_new: set[int] = set()
    for ratio, i, j in scored:
        if ratio <= SIMILARITY:
            break
        if i in paired_old or j in paired_new:
            continue
        paired_old.add(i)
        paired_new.add(j)
        entries.append(
            {
                "status": "changed",
                "old_id": old[i]["id"],
                "new_id": new[j]["id"],
                "old_index": i,
                "new_index": j,
                "similarity": round(ratio, 3),
            }
        )
    entries += [
        {
            "status": "removed",
            "old_id": old[i]["id"],
            "new_id": None,
            "old_index": i,
            "new_index": None,
            "similarity": 0.0,
        }
        for i in rest_old
        if i not in paired_old
    ]
    entries += [
        {
            "status": "added",
            "old_id": None,
            "new_id": new[j]["id"],
            "old_index": None,
            "new_index": j,
            "similarity": 0.0,
        }
        for j in rest_new
        if j not in paired_new
    ]
    entries.sort(
        key=lambda e: e["new_index"] if e["new_index"] is not None else e["old_index"] - 0.5
    )
    return entries
