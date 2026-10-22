"""Устойчивые идентификаторы абзацев брифа и карта абзацев между соседними версиями.

Шов: публичные операции ``knowledge`` (``ingest``, ``paragraphs``, ``paragraphMap``).
"""

from __future__ import annotations

import pytest

from src.office import knowledge
from src.office.storage import OfficeStore


@pytest.fixture
def store(tmp_path):
    s = OfficeStore(tmp_path / "office.db")
    try:
        yield s
    finally:
        s.close()


def _save(store: OfficeStore, pid: int, *paragraphs: str) -> int:
    result = knowledge.ingest(
        store, pid, kind="brief", markdown="\n\n".join(paragraphs), source="текст"
    )
    return result["version"]["number"]


def test_same_text_in_two_versions_has_same_paragraph_id(store) -> None:
    pid = store.create_project(name="Лендинг", created_by=1)["id"]
    v1 = _save(store, pid, "# Сайт", "Нужен лендинг.", "Срок месяц.")
    v2 = _save(store, pid, "# Сайт", "Нужен лендинг.", "Срок два месяца.")
    p1 = knowledge.paragraphs(store, pid, "brief", v1)
    p2 = knowledge.paragraphs(store, pid, "brief", v2)
    assert [p["text"] for p in p1] == ["# Сайт", "Нужен лендинг.", "Срок месяц."]
    assert p1[0]["id"] == p2[0]["id"]
    assert p1[1]["id"] == p2[1]["id"]
    assert p1[2]["id"] != p2[2]["id"]


def test_repeated_paragraph_in_one_version_gets_distinct_ids(store) -> None:
    pid = store.create_project(name="Лендинг", created_by=1)["id"]
    v1 = _save(store, pid, "Пункт.", "Другое.", "Пункт.")
    ids = [p["id"] for p in knowledge.paragraphs(store, pid, "brief", v1)]
    assert len(set(ids)) == 3


def _statuses(store, pid: int, number: int) -> list[tuple[str, str | None, str | None]]:
    old = {p["id"]: p["text"] for p in knowledge.paragraphs(store, pid, "brief", number - 1) or []}
    new = {p["id"]: p["text"] for p in knowledge.paragraphs(store, pid, "brief", number)}
    return sorted(
        (e["status"], old.get(e["old_id"]), new.get(e["new_id"]))
        for e in knowledge.paragraphMap(store, pid, "brief", number)
    )


def test_map_shows_insert_edit_and_delete(store) -> None:
    pid = store.create_project(name="Лендинг", created_by=1)["id"]
    _save(store, pid, "# Сайт", "Нужен лендинг с формой заявки.", "Срок месяц.", "Бюджет обсудим.")
    v2 = _save(
        store,
        pid,
        "# Сайт",
        "Нужен лендинг с формой заявки и картой.",
        "Контакты в подвале.",
        "Бюджет обсудим.",
    )
    assert _statuses(store, pid, v2) == sorted(
        [
            ("same", "# Сайт", "# Сайт"),
            (
                "changed",
                "Нужен лендинг с формой заявки.",
                "Нужен лендинг с формой заявки и картой.",
            ),
            ("removed", "Срок месяц.", None),
            ("added", None, "Контакты в подвале."),
            ("same", "Бюджет обсудим.", "Бюджет обсудим."),
        ]
    )


def test_map_shows_moved_paragraph(store) -> None:
    pid = store.create_project(name="Лендинг", created_by=1)["id"]
    _save(store, pid, "Первый абзац.", "Второй абзац.", "Третий абзац.")
    v2 = _save(store, pid, "Третий абзац.", "Первый абзац.", "Второй абзац.")
    assert _statuses(store, pid, v2) == sorted(
        [
            ("moved", "Третий абзац.", "Третий абзац."),
            ("same", "Первый абзац.", "Первый абзац."),
            ("same", "Второй абзац.", "Второй абзац."),
        ]
    )


def test_first_version_map_is_all_new(store) -> None:
    pid = store.create_project(name="Лендинг", created_by=1)["id"]
    v1 = _save(store, pid, "# Сайт", "Нужен лендинг.")
    assert [e["status"] for e in knowledge.paragraphMap(store, pid, "brief", v1)] == [
        "added",
        "added",
    ]
