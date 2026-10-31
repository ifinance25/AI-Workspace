"""Задачи Redmine в чате: права, подсчёт и подписанный черновик. Сети и ключа нет."""
from __future__ import annotations

import json

import pytest

from src.claude.session import SessionManager
from src.connections import redmine_tools
from src.office import redmine_mirror, tenancy
from src.office.storage import OfficeStore
from src.web.passwords import hash_password

_SECRET = "s" * 32


@pytest.fixture
def world(tmp_path):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    store = OfficeStore(sm.storage_path)
    pw = hash_password("test-only-password")
    ivan = sm.create_local_user(username="ivan", password_hash=pw, is_admin=False)
    stranger = sm.create_local_user(username="stranger", password_hash=pw, is_admin=False)
    customer = sm.create_local_user(username="customer", password_hash=pw, is_admin=False)
    root = sm.create_local_user(username="root", password_hash=pw, is_admin=True)
    project = store.create_project(name="Факт", created_by=ivan)
    tenancy.record_creator(store, project["id"], ivan)
    store.add_member(project["id"], customer, "customer_representative")
    redmine_mirror.seed_demo_mirror(store, project["id"])
    redmine_tools.register(store, sm, _SECRET)
    yield {"pid": project["id"], "ivan": ivan, "stranger": stranger, "customer": customer, "root": root}
    redmine_tools.unregister()
    store.close()
    sm.close_sync()


def _data(result: dict) -> dict:
    text = result["content"][0]["text"]
    return json.loads(text[text.index("{") :])


async def test_member_sees_project_and_counts(world) -> None:
    listed = await redmine_tools.call_tool("redmine_projects", {}, user_id=world["ivan"])
    assert _data(listed)["projects"][0]["issues"] == 10
    summary = await redmine_tools.call_tool(
        "redmine_summary", {"group_by": "status"}, user_id=world["ivan"]
    )
    body = _data(summary)
    assert body["total"] == 10
    assert body["open"] == 7  # три завершённые: у них посчитан цикл (cycle_hours)
    counts = {g["name"]: g["count"] for g in body["groups"]}
    assert counts["В работе"] == 3


async def test_search_filters_and_pages(world) -> None:
    found = await redmine_tools.call_tool(
        "redmine_search_issues", {"query": "оплат", "limit": 5}, user_id=world["ivan"]
    )
    assert [i["id"] for i in _data(found)["issues"]] == [104]
    open_only = await redmine_tools.call_tool(
        "redmine_search_issues", {"only_open": True, "limit": 3}, user_id=world["ivan"]
    )
    body = _data(open_only)
    assert body["total"] == 7 and len(body["issues"]) == 3


async def test_stranger_and_customer_see_nothing(world) -> None:
    for who in ("stranger", "customer"):
        result = await redmine_tools.call_tool("redmine_projects", {}, user_id=world[who])
        assert result["is_error"] is True
        issue = await redmine_tools.call_tool(
            "redmine_get_issue",
            {"project_id": world["pid"], "issue_id": 101},
            user_id=world[who],
        )
        assert issue["is_error"] is True


async def test_admin_sees_every_project(world) -> None:
    result = await redmine_tools.call_tool("redmine_projects", {}, user_id=world["root"])
    assert _data(result)["projects"][0]["project_id"] == world["pid"]


async def test_get_issue_marks_text_as_data(world) -> None:
    result = await redmine_tools.call_tool(
        "redmine_get_issue", {"project_id": world["pid"], "issue_id": 101}, user_id=world["ivan"]
    )
    text = result["content"][0]["text"]
    assert "не инструкция" in text
    assert _data(result)["subject"] == "Паспорт проекта"


async def test_propose_returns_signed_block_and_creates_nothing(world) -> None:
    result = await redmine_tools.call_tool(
        "redmine_propose_issue",
        {"project_id": world["pid"], "subject": "Новая тема", "due_date": "2026-12-01"},
        user_id=world["ivan"],
    )
    text = result["content"][0]["text"]
    assert "```pm-task" in text
    card = json.loads(text.split("```pm-task\n")[1].split("\n```")[0])
    assert redmine_mirror.verify_proposal(
        _SECRET, card["signature"], card["project_id"], world["ivan"],
        card["subject"], card["description"], card["due_date"],
    )
    # Чужой пользователь той же подписью создать не сможет.
    assert not redmine_mirror.verify_proposal(
        _SECRET, card["signature"], card["project_id"], world["stranger"],
        card["subject"], card["description"], card["due_date"],
    )
    # Изменённая тема ломает подпись.
    assert not redmine_mirror.verify_proposal(
        _SECRET, card["signature"], card["project_id"], world["ivan"],
        "Другая", card["description"], card["due_date"],
    )


async def test_propose_validates_and_refuses_foreign_project(world) -> None:
    bad_date = await redmine_tools.call_tool(
        "redmine_propose_issue",
        {"project_id": world["pid"], "subject": "x", "due_date": "01.12.2026"},
        user_id=world["ivan"],
    )
    assert bad_date["is_error"] is True
    foreign = await redmine_tools.call_tool(
        "redmine_propose_issue", {"project_id": world["pid"], "subject": "x"},
        user_id=world["stranger"],
    )
    assert foreign["is_error"] is True


def test_sdk_tools_empty_without_backend() -> None:
    redmine_tools.unregister()
    assert redmine_tools.sdk_tools(1) == []


def test_shared_server_exists_without_kb_when_redmine_tools_on(world) -> None:
    from types import SimpleNamespace

    from src.connections.resolver import SHARED_KB_SERVER_NAME, build_shared_mcp_servers

    settings = SimpleNamespace(
        claude=SimpleNamespace(transport="sdk"),
        get_kb_mcp_url=lambda: "",
        get_kb_mcp_key=lambda: "",
    )
    assert build_shared_mcp_servers(settings) == {}  # без пользователя лупа не включается
    servers = build_shared_mcp_servers(settings, user_id=world["ivan"])
    assert list(servers) == [SHARED_KB_SERVER_NAME]
