"""Хранилище офиса на временной SQLite: проект, участники с ролью, версии Markdown."""
from __future__ import annotations

import pytest

from src.office.storage import OfficeStore


@pytest.fixture
def store(tmp_path):
    s = OfficeStore(tmp_path / "sessions.db")
    try:
        yield s
    finally:
        s.close()


def test_project_passport_fields(store) -> None:
    project = store.create_project(
        name="Лендинг", created_by=7, work_kind="сайт", nature="разработка",
    )
    assert project["name"] == "Лендинг"
    assert project["work_kind"] == "сайт"
    assert project["nature"] == "разработка"
    # Тип и статус по умолчанию: маленький заказ, проект активен.
    assert project["project_type"] == "small"
    assert project["status"] == "active"
    assert project["created_by"] == 7

    updated = store.update_project(project["id"], project_type="large", status="paused")
    assert updated["project_type"] == "large"
    assert updated["status"] == "paused"
    with pytest.raises(ValueError):
        store.update_project(project["id"], created_by=1)


def test_members_with_role_and_repeat_changes_role(store) -> None:
    project = store.create_project(name="Бот", created_by=1)
    store.add_member(project["id"], 1, "project_manager")
    store.add_member(project["id"], 2, "developer")
    store.add_member(project["id"], 2, "tester")
    members = {m["user_id"]: m["role"] for m in store.list_members(project["id"])}
    assert members == {1: "project_manager", 2: "tester"}
    assert store.list_projects_for_user(2) == [project]
    assert store.list_projects_for_user(3) == []


def test_document_versions_are_numbered_and_keep_history(store) -> None:
    project = store.create_project(name="Бот", created_by=1)
    doc = store.ensure_document(project["id"], "brief")
    assert store.ensure_document(project["id"], "brief") == doc

    v1 = store.add_version(doc["id"], markdown="# Бриф", source="user", created_by=1)
    v2 = store.add_version(doc["id"], markdown="# Бриф v2", source="agent")
    assert (v1["number"], v2["number"]) == (1, 2)
    assert v1["status"] == "draft"
    assert v2["source"] == "agent"
    assert v2["created_at"]

    store.set_version_status(v1["id"], "accepted")
    assert [v["status"] for v in store.list_versions(doc["id"])] == ["accepted", "draft"]
    assert store.latest_version(doc["id"])["markdown"] == "# Бриф v2"
    # Принятая версия не переписана: текст первой версии на месте.
    assert store.get_version(v1["id"])["markdown"] == "# Бриф"


def test_data_survives_second_start(tmp_path) -> None:
    first = OfficeStore(tmp_path / "sessions.db")
    project = first.create_project(name="Лендинг", created_by=1)
    first.close()
    second = OfficeStore(tmp_path / "sessions.db")
    try:
        assert second.get_project(project["id"]) == project
    finally:
        second.close()
