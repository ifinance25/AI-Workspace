"""Зеркало Redmine: четыре вызова на подделке, без ключа и без сети."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.office import redmine_mirror, tenancy
from src.office.storage import OfficeStore
from src.web.passwords import hash_password
from src.web.server import WebServer

_PASSWORD = "test-only-password"
# Ключ шифрования секретов на тестовом сервере (У43-07), не секрет.
_CONN_KEY = Fernet.generate_key().decode()


class _Redmine:
    """Отвечает как Redmine. Сети нет."""

    def __init__(self) -> None:
        self.calls = 0
        self.id_list_calls = 0
        self.last_updated_since = None
        self.down = False
        self.updates = 0
        self.reads = 0
        self.saved_description = None
        self.incremental_issues: list[dict] = []
        self.users = {
            3: {"id": 3, "login": "ivan", "name": "Иван Петров"},
            4: {"id": 4, "login": "anna_redmine", "name": "Анна Смирнова"},
        }
        self.issues = [
            {
                "id": 15,
                "subject": "Оплата",
                "description": "Счёт за октябрь",
                "status": {"id": 2, "name": "В работе"},
                "author": {"id": 3, "name": "Иван Петров"},
                "assigned_to": {"id": 4, "name": "Анна"},
                "start_date": "2026-10-01",
                "due_date": "2026-10-20",
                "journals": [
                    {
                        "id": 9,
                        "created_on": "2026-10-02T10:00:00Z",
                        "notes": "Передал в работу",
                        "user": {"id": 3, "name": "Иван Петров"},
                        "details": [
                            {
                                "property": "attr",
                                "name": "status_id",
                                "old_value": "1",
                                "new_value": "2",
                            },
                            {
                                "property": "attr",
                                "name": "assigned_to_id",
                                "old_value": "3",
                                "new_value": "4",
                            },
                        ],
                    },
                    {
                        "id": 10,
                        "created_on": "2026-10-03T10:00:00Z",
                        "notes": "",
                        "user": {"id": 4, "name": "Анна"},
                        "details": [
                            {
                                "property": "attr",
                                "name": "subject",
                                "old_value": "A",
                                "new_value": "B",
                            }
                        ],
                    },
                ],
            }
        ]

    def list_issues(self, project: str, *, updated_since=None) -> list[dict]:
        self.calls += 1
        self.last_updated_since = updated_since
        if self.down:
            raise redmine_mirror.RedmineUnavailableError("нет связи")
        assert project == "fact"
        if updated_since is not None:
            return list(self.incremental_issues)
        return self.issues

    def list_issue_ids(self, project: str) -> set[int]:
        self.id_list_calls += 1
        if self.down:
            raise redmine_mirror.RedmineUnavailableError("нет связи")
        assert project == "fact"
        return {int(row["id"]) for row in self.issues}

    def get_user(self, user_id: int) -> dict:
        return self.users[user_id]

    def get_issue(self, issue_id: int) -> dict:
        self.reads += 1
        if self.down:
            raise redmine_mirror.RedmineUnavailableError("нет связи")
        assert issue_id == 15
        issue = self.issues[0]
        if self.saved_description is not None:
            issue = {**issue, "description": self.saved_description}
        return issue

    def update_issue(self, issue_id: int, fields: dict) -> None:
        self.updates += 1
        if self.down:
            raise redmine_mirror.RedmineUnavailableError("нет связи")
        assert issue_id == 15
        self.saved_description = "как сохранил Redmine"


def _office(tmp_path):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    store = OfficeStore(sm.storage_path)
    ivan = sm.create_local_user(
        username="ivan", password_hash=hash_password(_PASSWORD), is_admin=False
    )
    project = store.create_project(name="Факт", created_by=ivan)
    tenancy.record_creator(store, project["id"], ivan)
    return sm, store, project["id"], ivan


def test_seed_demo_mirror_served_without_api_key(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    count = redmine_mirror.seed_demo_mirror(store, pid)
    assert count >= 8

    class _NoKey:
        def list_issues(self, project: str, **kwargs) -> list:
            raise redmine_mirror.MirrorError("no_key", "Ключ Redmine не задан")

    loaded = redmine_mirror.load_project(
        store,
        pid,
        actor_id=ivan,
        is_admin=False,
        client=_NoKey(),
        users=sm,
        redmine_project="demo",
    )
    assert loaded["connected"] is True
    assert len(loaded["issues"]) == count


def test_kanban_lookups_returned_in_mirror_view(tmp_path) -> None:
    from src.office.redmine_mirror._lookups import default_fixture_path, seed_lookups

    sm, store, pid, ivan = _office(tmp_path)
    fixture = default_fixture_path()
    if not fixture.is_file():
        import pytest

        pytest.skip(f"нет фикстуры {fixture}")
    seed_lookups(store, fixture_path=fixture)
    redmine_mirror.seed_demo_mirror(store, pid)

    class _NoKey:
        def list_issues(self, project: str, **kwargs) -> list:
            raise redmine_mirror.MirrorError("no_key", "Ключ Redmine не задан")

    loaded = redmine_mirror.load_project(
        store,
        pid,
        actor_id=ivan,
        is_admin=False,
        client=_NoKey(),
        users=sm,
        redmine_project="demo",
    )
    lookups = loaded.get("lookups")
    assert lookups is not None
    assert any(item.get("name") == "Новая" for item in lookups.get("statuses", []))
    assert "Frontend" in lookups.get("types", [])


def test_create_demo_issue_without_redmine_key(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    redmine_mirror.seed_demo_mirror(store, pid)

    class _NoKey:
        def create_issue(self, project: str, fields: dict) -> dict:
            raise redmine_mirror.MirrorError("no_key", "Ключ Redmine не задан")

        def get_issue(self, issue_id: int) -> dict:
            raise AssertionError("не должен читать Redmine")

        def update_issue(self, issue_id: int, fields: dict) -> None:
            raise AssertionError("не должен обновлять Redmine")

    created = redmine_mirror.create_issue(
        store,
        pid,
        actor_id=ivan,
        is_admin=False,
        client=_NoKey(),
        users=sm,
        request_key="demo-create-1",
        redmine_project="demo-local",
        subject="Локальная задача",
        description="текст",
    )
    assert created["issue"]["subject"] == "Локальная задача"
    assert created["issue"]["id"] > 110


def test_load_copies_description_histories_comments_and_matches_login(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    before = {row["username"] for row in sm.list_users()}
    loaded = redmine_mirror.load_project(
        store,
        pid,
        actor_id=ivan,
        is_admin=False,
        client=_Redmine(),
        users=sm,
        redmine_project="fact",
    )
    issue = loaded["issues"][0]
    assert issue["id"] == 15
    assert issue["description"] == "Счёт за октябрь"
    assert issue["status_history"] == [
        {"at": "2026-10-02T10:00:00Z", "old": "1", "new": "2"}
    ]
    assert issue["assignee_history"] == [
        {"at": "2026-10-02T10:00:00Z", "old": "3", "new": "4"}
    ]
    assert [c["text"] for c in issue["comments"]] == ["Передал в работу"]
    assert issue["author"] == {"user_id": ivan, "login": "ivan", "name": "Иван Петров"}
    assert issue["assignee"]["user_id"] is None
    assert issue["assignee"]["name"] == "Анна"
    assert {row["username"] for row in sm.list_users()} == before
    assert "password_hash" not in str(loaded)
    store.close()
    sm.close_sync()


def test_mirror_snapshot_reads_db_without_redmine(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    client = _Redmine()
    redmine_mirror.load_project(
        store,
        pid,
        actor_id=ivan,
        is_admin=False,
        client=client,
        users=sm,
        redmine_project="fact",
    )
    client.calls = 0

    class _Broken:
        def list_issues(self, *args, **kwargs):
            raise AssertionError("snapshot не ходит в Redmine")

    snap = redmine_mirror.mirror_snapshot(
        store, pid, actor_id=ivan, is_admin=False
    )
    assert snap["issues"][0]["id"] == 15
    assert client.calls == 0
    store.close()
    sm.close_sync()


def test_second_load_is_incremental_and_merges(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    client = _Redmine()
    moment = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
    first = redmine_mirror.load_project(
        store,
        pid,
        actor_id=ivan,
        is_admin=False,
        client=client,
        users=sm,
        redmine_project="fact",
        now=moment,
    )
    assert len(first["issues"]) == 1
    assert client.calls == 1
    assert client.id_list_calls == 0

    client.incremental_issues = [
        {
            "id": 16,
            "subject": "Новая",
            "description": "",
            "status": {"id": 1, "name": "Новая"},
            "author": {"id": 3, "name": "Иван Петров"},
            "assigned_to": None,
            "start_date": None,
            "due_date": None,
            "journals": [],
        }
    ]
    client.issues.append(client.incremental_issues[0])

    second = redmine_mirror.load_project(
        store,
        pid,
        actor_id=ivan,
        is_admin=False,
        client=client,
        users=sm,
        redmine_project="fact",
        now=moment + timedelta(minutes=1),
    )
    assert client.calls == 2
    assert client.last_updated_since is not None
    assert client.id_list_calls == 1
    assert {issue["id"] for issue in second["issues"]} == {15, 16}
    store.close()
    sm.close_sync()


def test_schedule_is_fifteen_minutes_and_outage_keeps_the_copy(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    client = _Redmine()
    moment = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
    loaded = redmine_mirror.load_project(
        store, pid, actor_id=ivan, is_admin=False, client=client, users=sm,
        redmine_project="fact", now=moment,
    )
    assert loaded["interval_minutes"] == 15
    assert loaded["synced_at"] == "2026-10-30T12:00:00+00:00"
    assert loaded["next_sync_at"] == "2026-10-30T12:15:00+00:00"
    early = redmine_mirror.run_due(
        store, users=sm, now=moment + timedelta(minutes=14), client_factory=lambda _url: client
    )
    assert early == 0
    assert client.calls == 1
    client.down = True
    client.issues[0]["description"] = "свежий ответ, который нельзя показывать"
    due = redmine_mirror.run_due(
        store, users=sm, now=moment + timedelta(minutes=15), client_factory=lambda _url: client
    )
    assert due == 1
    again = redmine_mirror.load_project(
        store, pid, actor_id=ivan, is_admin=False, client=client, users=sm,
        redmine_project="fact", now=moment + timedelta(minutes=16),
    )
    assert again["updated"] is False
    assert again["message"] == "данные не обновились"
    assert again["issues"][0]["description"] == "Счёт за октябрь"
    assert again["synced_at"] == "2026-10-30T12:00:00+00:00"
    store.close()
    sm.close_sync()


def test_before_first_success_the_mirror_says_it_is_not_connected(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    client = _Redmine()
    client.down = True
    loaded = redmine_mirror.load_project(
        store, pid, actor_id=ivan, is_admin=False, client=client, users=sm,
        redmine_project="fact",
    )
    assert loaded["connected"] is False
    assert loaded["issues"] == []
    assert loaded["message"] == "Redmine ещё не подключён"
    assert loaded["interval_minutes"] == 15
    store.close()
    sm.close_sync()


class _Writer:
    def __init__(self) -> None:
        self.creates = 0
        self.updates = 0
        self.reads = 0
        self.fail = False
        self.empty = False
        self.card = {
            "id": 77,
            "subject": "Заявка",
            "description": "как записал Redmine",
            "status": {"id": 1, "name": "Новая"},
            "author": {"id": 3, "name": "Иван Петров", "login": "ivan"},
            "assigned_to": None,
            "journals": [],
        }

    def create_issue(self, project: str, fields: dict) -> dict:
        if self.fail:
            raise redmine_mirror.RedmineUnavailableError("нет связи")
        if self.empty:
            return {"issue": {}}
        self.creates += 1
        assert project == "fact"
        assert fields["subject"] == "Черновик"
        return {"issue": {"id": 77}}

    def get_issue(self, issue_id: int) -> dict:
        self.reads += 1
        assert issue_id == 77
        return self.card

    def update_issue(self, issue_id: int, fields: dict) -> None:
        self.updates += 1
        assert issue_id == 77
        self.card = {**self.card, "description": "правка из Redmine"}

    def get_user(self, user_id: int) -> dict:
        return {"id": user_id, "login": "ivan", "name": "Иван Петров"}


def _create(store, pid, ivan, sm, writer, key: str):
    return redmine_mirror.create_issue(
        store, pid, actor_id=ivan, is_admin=False, client=writer, users=sm,
        request_key=key, redmine_project="fact", subject="Черновик", description="мой текст",
    )


def test_create_reads_the_redmine_number_and_repeat_does_not_create_another(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    writer = _Writer()
    first = _create(store, pid, ivan, sm, writer, "save-1")
    assert first["issue"]["id"] == 77
    assert first["issue"]["description"] == "как записал Redmine"
    assert writer.creates == 1
    assert writer.reads == 1
    second = _create(store, pid, ivan, sm, writer, "save-1")
    assert second["issue"]["id"] == 77
    assert second["issue"]["description"] == "правка из Redmine"
    assert writer.creates == 1
    assert writer.updates == 1
    store.close()
    sm.close_sync()


def test_create_without_redmine_number_does_not_invent_one(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    writer = _Writer()
    writer.fail = True
    with pytest.raises(redmine_mirror.MirrorError) as failed:
        _create(store, pid, ivan, sm, writer, "save-1")
    assert failed.value.code == "unavailable"
    assert writer.reads == 0
    assert writer.creates == 0
    writer.fail = False
    writer.empty = True
    with pytest.raises(redmine_mirror.MirrorError) as empty:
        _create(store, pid, ivan, sm, writer, "save-2")
    assert empty.value.code == "no_number"
    assert writer.reads == 0
    writer.empty = False
    made = _create(store, pid, ivan, sm, writer, "save-2")
    assert made["issue"]["id"] == 77
    assert writer.creates == 1
    store.close()
    sm.close_sync()


def test_update_shows_what_redmine_saved_and_a_missed_answer_keeps_the_copy(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    client = _Redmine()
    redmine_mirror.load_project(
        store, pid, actor_id=ivan, is_admin=False, client=client, users=sm, redmine_project="fact"
    )
    updated = redmine_mirror.update_issue(
        store, pid, 15, actor_id=ivan, is_admin=False, client=client, users=sm,
        description="мой текст",
    )
    assert updated["issue"]["id"] == 15
    assert updated["issue"]["description"] == "как сохранил Redmine"
    client.down = True
    with pytest.raises(redmine_mirror.MirrorError) as missed:
        redmine_mirror.update_issue(
            store, pid, 15, actor_id=ivan, is_admin=False, client=client, users=sm,
            description="ещё текст",
        )
    assert missed.value.code == "unavailable"
    kept = redmine_mirror.load_issue(
        store, pid, 15, actor_id=ivan, is_admin=False, client=client, users=sm
    )
    assert kept["updated"] is False
    assert kept["message"] == "данные не обновились"
    assert kept["issue"]["description"] == "как сохранил Redmine"
    store.close()
    sm.close_sync()


def test_customer_and_foreign_project_are_refused(tmp_path) -> None:
    sm, store, pid, ivan = _office(tmp_path)
    client = _Redmine()
    customer = sm.create_local_user(
        username="cust", password_hash=hash_password(_PASSWORD), is_admin=False
    )
    store.add_member(pid, customer, "customer_representative")
    outsider = sm.create_local_user(
        username="outsider", password_hash=hash_password(_PASSWORD), is_admin=False
    )
    with pytest.raises(redmine_mirror.MirrorError) as refused:
        redmine_mirror.load_project(
            store, pid, actor_id=customer, is_admin=False, client=client, users=sm,
            redmine_project="fact",
        )
    assert refused.value.code == "customer"
    with pytest.raises(redmine_mirror.MirrorError) as foreign:
        redmine_mirror.create_issue(
            store, pid, actor_id=outsider, is_admin=False, client=client, users=sm,
            request_key="save-1", redmine_project="fact", subject="Чужая",
        )
    assert foreign.value.code == "not_found"
    assert client.calls == 0
    store.close()
    sm.close_sync()


def test_open_client_without_key_does_not_call_the_network(monkeypatch) -> None:
    monkeypatch.delenv("REDMINE_API_KEY", raising=False)
    with pytest.raises(redmine_mirror.MirrorError) as missing:
        redmine_mirror.open_client("https://redmine.example")
    assert missing.value.code == "no_key"


@pytest.fixture
def server(tmp_path):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    settings = WebSettings(
        enabled=True, host="127.0.0.1", port=0, jwt_secret="x" * 32, telegram_bot_username="t"
    )
    srv = WebServer(
        settings=settings, allowed_user_ids=[], bot_username="t", session_manager=sm,
        event_bus=EventBus(), jwt_secret="x" * 32, connections_secret_key=_CONN_KEY,
    )
    try:
        yield srv, sm
    finally:
        srv.office_store.close()
        sm.close_sync()
        sm._engine.sync_engine.dispose()


def _member(srv: WebServer, sm: SessionManager, username: str, role: str) -> int:
    uid = sm.create_local_user(
        username=username, password_hash=hash_password(_PASSWORD), is_admin=False
    )
    project = srv.office_store.create_project(name=f"Проект {username}", created_by=uid)
    if role == "project_manager":
        tenancy.record_creator(srv.office_store, project["id"], uid)
    else:
        srv.office_store.add_member(project["id"], uid, role)
    return project["id"]


@asynccontextmanager
async def _client(srv: WebServer, username: str):
    async with AsyncClient(transport=ASGITransport(app=srv.app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login", json={"username": username, "password": _PASSWORD}
        )
        assert response.status_code == 200
        yield client


async def test_http_refuses_customer_and_foreign_project(server) -> None:
    srv, sm = server
    pid = _member(srv, sm, "lead", "project_manager")
    customer = sm.create_local_user(
        username="cust", password_hash=hash_password(_PASSWORD), is_admin=False
    )
    srv.office_store.add_member(pid, customer, "customer_signatory")
    sm.create_local_user(
        username="outsider", password_hash=hash_password(_PASSWORD), is_admin=False
    )
    body = {"redmine_project": "fact", "base_url": "https://redmine.example"}
    async with _client(srv, "cust") as client:
        loaded = await client.post(f"/api/office/projects/{pid}/redmine/load", json=body)
        created = await client.post(
            f"/api/office/projects/{pid}/redmine/issues",
            json={**body, "request_key": "save-1", "subject": "Новая"},
        )
        changed = await client.put(
            f"/api/office/projects/{pid}/redmine/issues/15", json={"description": "текст"}
        )
        one = await client.post(
            f"/api/office/projects/{pid}/redmine/issues/15/load", json={}
        )
    async with _client(srv, "outsider") as client:
        foreign = await client.post(f"/api/office/projects/{pid}/redmine/load", json=body)
    assert loaded.status_code == 403
    assert created.status_code == 403
    assert changed.status_code == 403
    assert one.status_code == 403
    assert foreign.status_code == 404


async def test_app_start_runs_the_fifteen_minute_sync(server, monkeypatch) -> None:
    srv, _sm = server
    seen: dict[str, bool] = {}

    def _fake_due(store, *, users, now=None, client_factory=None) -> int:
        seen["ran"] = True
        return 0

    monkeypatch.setattr(redmine_mirror, "run_due", _fake_due)
    async with srv.app.router.lifespan_context(srv.app):
        for _ in range(20):
            if seen.get("ran"):
                break
            await asyncio.sleep(0.01)
    assert seen.get("ran") is True


def _journal(journal_id: int, at: str, new_status: str, old_status: str = "1") -> dict:
    return {
        "id": journal_id,
        "created_on": at,
        "notes": "",
        "user": {"id": 3, "name": "Иван Петров"},
        "details": [{
            "property": "attr",
            "name": "status_id",
            "old_value": old_status,
            "new_value": new_status,
        }],
    }


def test_section_and_cycle_hours_follow_the_dashboard_rules(tmp_path) -> None:
    """Раздел по словам сборки, часы по календарю РФ. Числа разобраны вручную.

    Пятница 30.10 17:00 до понедельника 02.11 10:00: час до 18:00 и час с 09:00,
    выходные пустые, вместе 2. Короткий день 30.04 кончается в 17:00, с 16:00
    до 17:30 это 1 час. Праздник 01.05 даёт 0. С 09:00 до 15:00 обед вычитается,
    остаётся 5. Открытая задача часов цикла не имеет.
    """
    sm, store, pid, ivan = _office(tmp_path)
    client = _Redmine()
    client.issues = [
        {
            "id": 31,
            "subject": "Статья про сотрудника",
            "description": "",
            "status": {"id": 5, "name": "Закрыта"},
            "author": {"id": 3, "name": "Иван Петров"},
            "journals": [
                _journal(1, "2026-10-30T17:00:00+03:00", "2"),
                _journal(2, "2026-11-02T10:00:00+03:00", "5", "2"),
            ],
        },
        {
            "id": 32,
            "subject": "спасибо",
            "description": "",
            "status": {"id": 6, "name": "Отклонена"},
            "author": {"id": 3, "name": "Иван Петров"},
            "journals": [
                _journal(1, "2026-04-30T16:00:00+03:00", "2"),
                _journal(2, "2026-04-30T17:30:00+03:00", "6", "2"),
            ],
        },
        {
            "id": 33,
            "subject": "база знаний",
            "description": "",
            "status": {"id": 5, "name": "Закрыта"},
            "author": {"id": 3, "name": "Иван Петров"},
            "created_on": "2026-05-01T07:00:00Z",
            "journals": [
                _journal(1, "2026-05-01T10:00:00+03:00", "2"),
                _journal(2, "2026-05-01T16:00:00+03:00", "5", "2"),
            ],
        },
        {
            "id": 34,
            "subject": "идея сообщества",
            "description": "",
            "status": {"id": 5, "name": "Закрыта"},
            "author": {"id": 3, "name": "Иван Петров"},
            "start_date": "2026-10-30",
            "created_on": "2026-10-30T06:00:00Z",
            "journals": [_journal(1, "2026-10-30T15:00:00+03:00", "5")],
        },
        {
            "id": 35,
            "subject": "курс",
            "description": "",
            "status": {"id": 2, "name": "В работе"},
            "author": {"id": 3, "name": "Иван Петров"},
            "journals": [_journal(1, "2026-10-26T10:00:00+03:00", "2")],
        },
    ]
    loaded = redmine_mirror.load_project(
        store, pid, actor_id=ivan, is_admin=False, client=client, users=sm,
        redmine_project="fact",
    )
    by_id = {item["id"]: item for item in loaded["issues"]}
    assert by_id[31]["ftt_section"] == "База знаний"
    assert by_id[31]["cycle_hours"] == 2
    assert by_id[32]["ftt_section"] == "Спасибо"
    assert by_id[32]["cycle_hours"] == 1
    assert by_id[33]["ftt_section"] == "Не определён"
    assert by_id[33]["cycle_hours"] == 0
    assert by_id[34]["ftt_section"] == "Общение единомышленников"
    assert by_id[34]["cycle_hours"] == 5
    assert by_id[35]["ftt_section"] == "Управление электронным обучением"
    assert by_id[35]["cycle_hours"] is None
    store.close()
    sm.close_sync()


def test_admin_token_is_not_returned(tmp_path) -> None:
    store = OfficeStore(tmp_path / "office.db")
    cipher = redmine_mirror.cipher_from_key(_CONN_KEY)
    saved = redmine_mirror.save_account(
        store, cipher,
        base_url="https://redmine.example",
        redmine_project="hr",
        api_key="secret-token-1234",
    )
    assert saved["has_token"] is True
    assert saved["last4"] == "1234"
    assert "secret-token" not in str(saved)
    kept = redmine_mirror.save_account(
        store, cipher,
        base_url="https://redmine.example",
        redmine_project="hr",
        api_key=None,
    )
    assert kept["last4"] == "1234"
    url, project, key = redmine_mirror.resolve_access(store, cipher, "", "")
    assert url == "https://redmine.example"
    assert project == "hr"
    assert key == "secret-token-1234"
    stolen = redmine_mirror.resolve_access(
        store, cipher, "https://evil.example", "other"
    )
    assert stolen[0] == "https://redmine.example"
    assert "evil" not in stolen[0]
    store.close()


async def test_member_cannot_send_saved_key_to_own_host(server, monkeypatch) -> None:
    srv, sm = server
    pid = _member(srv, sm, "lead", "project_manager")
    cipher = redmine_mirror.cipher_from_key(_CONN_KEY)
    redmine_mirror.save_account(
        srv.office_store, cipher,
        base_url="https://redmine.example",
        redmine_project="hr",
        api_key="secret-token-1234",
    )
    seen: dict[str, str] = {}

    class _Capture:
        def __init__(self, base_url: str, api_key: str) -> None:
            seen["url"] = base_url
            seen["key"] = api_key

        def list_issues(self, project: str, **kwargs) -> list[dict]:
            return []

        def list_issue_ids(self, project: str) -> set[int]:
            return set()

        def get_issue(self, issue_id: int) -> dict:
            return {"id": issue_id, "subject": "x"}

        def create_issue(self, project: str, fields: dict) -> dict:
            return {"issue": {"id": 1}}

        def update_issue(self, issue_id: int, fields: dict) -> None:
            return None

        def get_user(self, user_id: int) -> dict:
            return {}

    monkeypatch.setattr("src.office.redmine_mirror._http.HttpRedmine", _Capture)
    async with _client(srv, "lead") as client:
        loaded = await client.post(
            f"/api/office/projects/{pid}/redmine/load",
            json={"redmine_project": "hr", "base_url": "https://evil.example/steal"},
        )
    assert loaded.status_code == 200
    assert seen["url"] == "https://redmine.example"
    assert seen["key"] == "secret-token-1234"
    assert "evil" not in seen["url"]


async def test_http_admin_redmine_hides_token(server) -> None:
    srv, sm = server
    sm.create_local_user(
        username="boss", password_hash=hash_password(_PASSWORD), is_admin=True
    )
    sm.create_local_user(
        username="plain", password_hash=hash_password(_PASSWORD), is_admin=False
    )
    async with _client(srv, "plain") as plain:
        denied = await plain.get("/api/admin/redmine")
        assert denied.status_code == 403
    async with _client(srv, "boss") as boss:
        saved = await boss.put(
            "/api/admin/redmine",
            json={
                "base_url": "https://redmine.example",
                "redmine_project": "hr",
                "api_key": "secret-token-9876",
            },
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body["last4"] == "9876"
        assert "secret-token" not in saved.text
        again = await boss.get("/api/admin/redmine")
        assert again.json()["has_token"] is True
        assert "secret-token" not in again.text
