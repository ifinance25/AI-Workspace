"""Схема офиса: таблицы office_* живут в той же SQLite-базе, что и чаты.

Создание идемпотентное: второй старт на той же базе ничего не ломает.
"""
from __future__ import annotations

import sqlite3

from src.office.storage import OfficeStore

# Ожидаемый набор таблиц взят из плана (interfaces.md, решения среза A):
# проект офиса, участники, документ и его версии Markdown. Префикс office_.
EXPECTED_TABLES = {
    "office_projects",
    "office_members",
    "office_documents",
    "office_document_versions",
}


def _table_names(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


def test_office_tables_created_in_chat_database(make_mgr) -> None:
    sm = make_mgr()
    store = OfficeStore(sm.storage_path)
    try:
        names = _table_names(sm.storage_path)
    finally:
        store.close()
    assert EXPECTED_TABLES <= names
    # Та же база, что у чатов: рядом лежит таблица users менеджера сессий.
    assert "users" in names


def test_second_start_keeps_schema(make_mgr) -> None:
    sm = make_mgr()
    first = OfficeStore(sm.storage_path)
    first.close()
    second = OfficeStore(sm.storage_path)
    try:
        names = _table_names(sm.storage_path)
    finally:
        second.close()
    assert EXPECTED_TABLES <= names
