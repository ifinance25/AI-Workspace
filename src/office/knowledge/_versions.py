"""Версии Markdown документов проекта. ``knowledge`` единственный их писатель."""

from __future__ import annotations

from pathlib import PurePath

from src.office.knowledge import _paragraphs

TEXT_SOURCE = "текст"


class IngestError(ValueError):
    """Вход не стал версией. ``code``: ``empty`` | ``unsupported`` | ``too_large``."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _summary(version: dict) -> dict:
    return {key: version[key] for key in ("id", "number", "status", "source", "created_at")}


def ingest(
    store, project_id: int, *, kind: str, markdown: str, source: str, created_by: int | None = None
) -> dict:
    """Новая версия документа ``kind`` из Markdown: ``{"version", "created"}``.

    Пустой текст версию не создаёт. Тот же текст, что у последней версии, тоже:
    вернётся последняя с ``created=False``.
    """
    if not markdown.strip():
        raise IngestError(
            "empty",
            "Бриф пустой. Положите бриф: вставьте текст или загрузите файл .md, .txt, .docx.",
        )
    document = store.ensure_document(project_id, kind)
    latest = store.latest_version(document["id"])
    if latest is not None and latest["markdown"] == markdown:
        return {"version": _summary(latest), "created": False}
    version = store.add_version(
        document["id"],
        markdown=markdown,
        source=source,
        created_by=created_by,
    )
    _paragraphs.save(store, version["id"], markdown)
    return {"version": _summary(version), "created": True}


def versions(store, project_id: int, kind: str) -> list[dict]:
    """Версии документа без текста, по возрастанию номера; нет документа: пусто."""
    document = store.get_document(project_id, kind)
    if document is None:
        return []
    return [_summary(v) for v in store.list_versions(document["id"])]


def _find(store, project_id: int, kind: str, number: int) -> dict | None:
    document = store.get_document(project_id, kind)
    if document is None:
        return None
    return next((v for v in store.list_versions(document["id"]) if v["number"] == number), None)


def version(store, project_id: int, kind: str, number: int) -> dict | None:
    """Версия по номеру: текст Markdown и абзацы ``[{"id", "text"}]``; нет такой: ``None``."""
    found = _find(store, project_id, kind, number)
    if found is None:
        return None
    return {
        **_summary(found),
        "markdown": found["markdown"],
        "paragraphs": _paragraphs.load(store, found["id"], found["markdown"]),
    }


def paragraphs(store, project_id: int, kind: str, number: int) -> list[dict] | None:
    """Абзацы версии ``[{"id", "text"}]`` с устойчивыми идентификаторами."""
    found = version(store, project_id, kind, number)
    return None if found is None else found["paragraphs"]


def paragraph_map(store, project_id: int, kind: str, number: int) -> list[dict] | None:
    """Карта абзацев от версии ``number - 1`` к ``number``; у первой версии всё ``added``."""
    new = paragraphs(store, project_id, kind, number)
    if new is None:
        return None
    old = paragraphs(store, project_id, kind, number - 1) or []
    return _paragraphs.build_map(old, new)


def ingest_file(
    store, project_id: int, *, kind: str, filename: str, data: bytes, created_by: int | None = None
) -> dict:
    """Файл ``.md`` / ``.txt`` / ``.docx`` в Markdown и в версию; источник: имя файла."""
    from src.office.knowledge._parse import to_markdown

    name = PurePath(filename).name
    return ingest(
        store,
        project_id,
        kind=kind,
        markdown=to_markdown(name, data),
        source=name,
        created_by=created_by,
    )
