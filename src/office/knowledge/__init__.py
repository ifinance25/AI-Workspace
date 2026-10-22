"""Граница knowledge: версии Markdown, поиск, граф связей, экспорт.

Публичные операции по спецификации: ``ingest``, ``search``, ``graph``, ``export``.
В срезе A канон версии документа это текст Markdown в таблице
``office_document_versions``; файл ``.md`` на диске, поиск и граф: срез C.
``knowledge`` единственный писатель документов и версий.
"""

from src.office.knowledge._parse import ACCEPTED
from src.office.knowledge._versions import (
    TEXT_SOURCE,
    IngestError,
    ingest,
    ingest_file,
    paragraph_map,
    paragraphs,
    version,
    versions,
)

# Имя операции границы как в спецификации.
paragraphMap = paragraph_map  # noqa: N816

__all__ = [
    "ACCEPTED",
    "TEXT_SOURCE",
    "IngestError",
    "ingest",
    "ingest_file",
    "paragraphMap",
    "paragraph_map",
    "paragraphs",
    "version",
    "versions",
]
