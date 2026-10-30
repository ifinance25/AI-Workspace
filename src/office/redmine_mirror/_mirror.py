"""Локальная копия задач Redmine. Номер задачи это номер Redmine.

Ключ API сюда не входит: его читает HTTP-клиент из окружения и в базу не пишет.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from src.office import tenancy

SYNC_INTERVAL_MINUTES = 15
CUSTOMER_ROLES = frozenset({"customer_representative", "customer_signatory"})
NOT_CONNECTED = "Redmine ещё не подключён"
NOT_UPDATED = "данные не обновились"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS office_redmine_mirrors (
    project_id INTEGER PRIMARY KEY,
    redmine_project TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    last_ok_at TEXT,
    stale_message TEXT NOT NULL DEFAULT '',
    connected INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS office_redmine_issues (
    project_id INTEGER NOT NULL,
    issue_id INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (project_id, issue_id)
);
CREATE TABLE IF NOT EXISTS office_redmine_creates (
    project_id INTEGER NOT NULL,
    request_key TEXT NOT NULL,
    issue_id INTEGER,
    PRIMARY KEY (project_id, request_key)
);
"""

_DOWN = (TimeoutError, OSError, ConnectionError)
_inflight: set[tuple[int, str]] = set()
_CARD = (
    "subject",
    "description",
    "status_id",
    "assigned_to_id",
    "start_date",
    "due_date",
    "notes",
)


class MirrorError(Exception):
    """Отказ зеркала. ``code`` читает роутер, текст видит человек."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class RedmineUnavailableError(MirrorError):
    def __init__(self, message: str = "Redmine не ответил"):
        super().__init__("unavailable", message)


def _ensure(store: Any) -> None:
    with store._lock:
        conn = store._connection()
        conn.executescript(_SCHEMA)
        conn.commit()


def _clock(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _guard(store: Any, project_id: int, *, actor_id: int, is_admin: bool) -> None:
    member = store.get_member(project_id, actor_id)
    if member is not None and member["role"] in CUSTOMER_ROLES:
        raise MirrorError("customer", "Заказчик не открывает задачи Redmine")
    project = tenancy.open_project(store, project_id, actor_id=actor_id, is_admin=is_admin)
    if project is None:
        raise MirrorError("not_found", "Проект не найден")


def _person(client: Any, raw: dict | None, users: Any, cache: dict) -> dict | None:
    if not raw:
        return None
    name = str(raw.get("name") or "")
    login = str(raw.get("login") or "")
    remote_id = raw.get("id")
    if not login and remote_id is not None and hasattr(client, "get_user"):
        if remote_id not in cache:
            try:
                cache[remote_id] = client.get_user(int(remote_id)) or {}
            except (MirrorError, *_DOWN, KeyError, TypeError, ValueError):
                cache[remote_id] = {}
        found = cache[remote_id]
        login = str(found.get("login") or "")
        if not name:
            name = str(found.get("name") or "")
    linked = users.get_user_by_username(login) if login else None
    platform_id = None
    if linked is not None and linked.get("is_active", 1):
        platform_id = int(linked["user_id"])
    return {"user_id": platform_id, "login": login, "name": name}


def _history(journals: list, field: str) -> list[dict]:
    rows = []
    for journal in journals or []:
        at = journal.get("created_on") or ""
        for detail in journal.get("details") or []:
            if detail.get("name") != field:
                continue
            old = detail.get("old_value")
            new = detail.get("new_value")
            rows.append({
                "at": at,
                "old": "" if old is None else str(old),
                "new": "" if new is None else str(new),
            })
    return rows


def _comments(client: Any, journals: list, users: Any, cache: dict) -> list[dict]:
    rows = []
    for journal in journals or []:
        text = journal.get("notes") or ""
        if not str(text).strip():
            continue
        rows.append({
            "id": journal.get("id"),
            "text": text,
            "at": journal.get("created_on") or "",
            "author": _person(client, journal.get("user"), users, cache),
        })
    return rows


def _number(raw_id: Any) -> int:
    try:
        return int(raw_id)
    except (TypeError, ValueError) as exc:
        raise MirrorError("no_number", "Redmine не вернул номер задачи") from exc


def _issue_from_redmine(client: Any, raw: dict, users: Any, cache: dict) -> dict:
    if not isinstance(raw, dict) or raw.get("id") is None:
        raise MirrorError("no_number", "Redmine не вернул номер задачи")
    status = raw.get("status") or {}
    journals = raw.get("journals") or []
    return {
        "id": _number(raw.get("id")),
        "subject": raw.get("subject") or "",
        "description": raw.get("description") or "",
        "status": {"id": "" if status.get("id") is None else str(status.get("id")),
                   "name": status.get("name") or ""},
        "author": _person(client, raw.get("author"), users, cache),
        "assignee": _person(client, raw.get("assigned_to"), users, cache),
        "start_date": raw.get("start_date") or None,
        "due_date": raw.get("due_date") or None,
        "comments": _comments(client, journals, users, cache),
        "status_history": _history(journals, "status_id"),
        "assignee_history": _history(journals, "assigned_to_id"),
    }


def _row(store: Any, project_id: int) -> dict | None:
    with store._lock:
        found = store._connection().execute(
            "SELECT * FROM office_redmine_mirrors WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    return dict(found) if found is not None else None


def _issues(store: Any, project_id: int) -> list[dict]:
    with store._lock:
        rows = store._connection().execute(
            "SELECT payload FROM office_redmine_issues WHERE project_id = ? ORDER BY issue_id",
            (project_id,),
        ).fetchall()
    return [json.loads(row["payload"]) for row in rows]


def _one(store: Any, project_id: int, issue_id: int) -> dict | None:
    with store._lock:
        found = store._connection().execute(
            "SELECT payload FROM office_redmine_issues "
            "WHERE project_id = ? AND issue_id = ?",
            (project_id, issue_id),
        ).fetchone()
    return json.loads(found["payload"]) if found is not None else None


def _save(conn: Any, project_id: int, issue: dict) -> None:
    conn.execute(
        "INSERT INTO office_redmine_issues (project_id, issue_id, payload) VALUES (?, ?, ?) "
        "ON CONFLICT(project_id, issue_id) DO UPDATE SET payload = excluded.payload",
        (project_id, int(issue["id"]), json.dumps(issue, ensure_ascii=False)),
    )


def _schedule(last_ok_at: str | None) -> dict:
    base = {
        "interval_minutes": SYNC_INTERVAL_MINUTES,
        "synced_at": last_ok_at,
        "next_sync_at": None,
    }
    if not last_ok_at:
        return base
    last = datetime.fromisoformat(last_ok_at)
    base["next_sync_at"] = _iso(last + timedelta(minutes=SYNC_INTERVAL_MINUTES))
    return base


def _view(store: Any, project_id: int, *, updated: bool, message: str) -> dict:
    row = _row(store, project_id)
    return {
        "connected": bool(row and row["connected"]),
        "updated": updated,
        "message": message,
        "issues": _issues(store, project_id),
        **_schedule(row["last_ok_at"] if row else None),
    }


def _mark(
    conn: Any, project_id: int, *, redmine_project: str, base_url: str, moment: datetime
) -> None:
    conn.execute(
        "INSERT INTO office_redmine_mirrors "
        "(project_id, redmine_project, base_url, last_ok_at, stale_message, connected) "
        "VALUES (?, ?, ?, ?, '', 1) "
        "ON CONFLICT(project_id) DO UPDATE SET "
        "redmine_project = excluded.redmine_project, "
        "base_url = CASE WHEN excluded.base_url = '' THEN office_redmine_mirrors.base_url "
        "ELSE excluded.base_url END, "
        "last_ok_at = excluded.last_ok_at, stale_message = '', connected = 1",
        (project_id, redmine_project, base_url, _iso(moment)),
    )


def _stale(
    store: Any, project_id: int, message: str, *, redmine_project: str = "", base_url: str = ""
) -> None:
    with store._lock:
        conn = store._connection()
        conn.execute(
            "INSERT INTO office_redmine_mirrors "
            "(project_id, redmine_project, base_url, last_ok_at, stale_message, connected) "
            "VALUES (?, ?, ?, NULL, ?, 0) "
            "ON CONFLICT(project_id) DO UPDATE SET stale_message = excluded.stale_message",
            (project_id, redmine_project, base_url, message),
        )
        conn.commit()


def _keep(store: Any, project_id: int, *, redmine_project: str = "", base_url: str = "") -> dict:
    row = _row(store, project_id)
    if row and row["connected"]:
        _stale(store, project_id, NOT_UPDATED)
        return _view(store, project_id, updated=False, message=NOT_UPDATED)
    _stale(
        store, project_id, NOT_CONNECTED, redmine_project=redmine_project, base_url=base_url
    )
    return _view(store, project_id, updated=False, message=NOT_CONNECTED)


def load_project(
    store: Any,
    project_id: int,
    *,
    actor_id: int,
    is_admin: bool,
    client: Any,
    users: Any,
    redmine_project: str,
    base_url: str = "",
    now: datetime | None = None,
) -> dict:
    """Забрать задачи проекта: описание, истории статуса и «Назначена», комментарии."""
    _ensure(store)
    _guard(store, project_id, actor_id=actor_id, is_admin=is_admin)
    moment = _clock(now)
    try:
        raw_issues = client.list_issues(redmine_project)
    except (RedmineUnavailableError, *_DOWN):
        return _keep(store, project_id, redmine_project=redmine_project, base_url=base_url)
    cache: dict = {}
    parsed = [_issue_from_redmine(client, raw, users, cache) for raw in raw_issues]
    with store._lock:
        conn = store._connection()
        conn.execute("DELETE FROM office_redmine_issues WHERE project_id = ?", (project_id,))
        for issue in parsed:
            _save(conn, project_id, issue)
        _mark(
            conn, project_id, redmine_project=redmine_project, base_url=base_url, moment=moment
        )
        conn.commit()
    return _view(store, project_id, updated=True, message="")


def load_issue(
    store: Any,
    project_id: int,
    issue_id: int,
    *,
    actor_id: int,
    is_admin: bool,
    client: Any,
    users: Any,
) -> dict:
    """Забрать одну задачу по номеру Redmine и заменить только её копию."""
    _ensure(store)
    _guard(store, project_id, actor_id=actor_id, is_admin=is_admin)
    number = int(issue_id)
    try:
        raw = client.get_issue(number)
    except (RedmineUnavailableError, *_DOWN):
        previous = _one(store, project_id, number)
        row = _row(store, project_id)
        if previous is not None and row and row["connected"]:
            _stale(store, project_id, NOT_UPDATED)
            return {"updated": False, "message": NOT_UPDATED, "issue": previous}
        raise MirrorError("unavailable", NOT_CONNECTED) from None
    issue = _issue_from_redmine(client, raw, users, {})
    if issue["id"] != number:
        raise MirrorError("no_number", "Redmine вернул другую задачу")
    with store._lock:
        conn = store._connection()
        _save(conn, project_id, issue)
        conn.commit()
    return {"updated": True, "message": "", "issue": issue}


def _fields(values: dict) -> dict:
    body = {}
    for key in _CARD:
        if values.get(key) is not None:
            body[key] = values[key]
    return body


def _known(store: Any, project_id: int, request_key: str) -> int | None:
    with store._lock:
        found = store._connection().execute(
            "SELECT issue_id FROM office_redmine_creates WHERE project_id = ? AND request_key = ?",
            (project_id, request_key),
        ).fetchone()
    if found is None or found["issue_id"] is None:
        return None
    return int(found["issue_id"])


def _remember(store: Any, project_id: int, request_key: str, issue_id: int) -> None:
    with store._lock:
        conn = store._connection()
        conn.execute(
            "INSERT INTO office_redmine_creates (project_id, request_key, issue_id) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(project_id, request_key) DO UPDATE SET issue_id = excluded.issue_id",
            (project_id, request_key, issue_id),
        )
        conn.commit()


def _pull(store: Any, project_id: int, issue_id: int, client: Any, users: Any) -> dict:
    try:
        raw = client.get_issue(int(issue_id))
    except (RedmineUnavailableError, *_DOWN) as exc:
        raise MirrorError("unavailable", NOT_UPDATED) from exc
    issue = _issue_from_redmine(client, raw, users, {})
    if issue["id"] != int(issue_id):
        raise MirrorError("no_number", "Redmine вернул другую задачу")
    with store._lock:
        conn = store._connection()
        _save(conn, project_id, issue)
        conn.commit()
    return issue


def create_issue(
    store: Any,
    project_id: int,
    *,
    actor_id: int,
    is_admin: bool,
    client: Any,
    users: Any,
    request_key: str,
    redmine_project: str,
    subject: str,
    description: str = "",
    status_id: str | int | None = None,
    assigned_to_id: int | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
    notes: str | None = None,
    base_url: str = "",
    now: datetime | None = None,
) -> dict:
    """Создать задачу в Redmine и сразу прочитать её по полученному номеру.

    Повтор того же ``request_key`` вторую задачу не создаёт: если номер уже есть,
    уходит правка этой задачи. Без ответа номер не записывается.
    """
    _ensure(store)
    _guard(store, project_id, actor_id=actor_id, is_admin=is_admin)
    if not str(request_key).strip():
        raise MirrorError("no_number", "Нет ключа запроса")
    card = _fields({
        "subject": subject,
        "description": description,
        "status_id": status_id,
        "assigned_to_id": assigned_to_id,
        "start_date": start_date,
        "due_date": due_date,
        "notes": notes,
    })
    known = _known(store, project_id, request_key)
    if known is not None:
        try:
            client.update_issue(known, card)
        except (RedmineUnavailableError, *_DOWN) as exc:
            raise MirrorError("unavailable", "Redmine не ответил") from exc
        return {"updated": True, "issue": _pull(store, project_id, known, client, users)}

    token = (int(project_id), request_key)
    with store._lock:
        if token in _inflight:
            raise MirrorError("pending", "Сохранение ещё не подтверждено Redmine")
        _inflight.add(token)
    try:
        try:
            created = client.create_issue(redmine_project, card)
        except (RedmineUnavailableError, *_DOWN) as exc:
            raise MirrorError("unavailable", "Redmine не ответил") from exc
        raw_issue = created.get("issue") if isinstance(created, dict) else None
        if not isinstance(raw_issue, dict) or raw_issue.get("id") is None:
            raise MirrorError("no_number", "Redmine не вернул номер задачи")
        number = _number(raw_issue.get("id"))
        _remember(store, project_id, request_key, number)
        issue = _pull(store, project_id, number, client, users)
        with store._lock:
            conn = store._connection()
            _mark(
                conn,
                project_id,
                redmine_project=redmine_project,
                base_url=base_url,
                moment=_clock(now),
            )
            conn.commit()
        return {"updated": True, "issue": issue}
    finally:
        _inflight.discard(token)


def update_issue(
    store: Any,
    project_id: int,
    issue_id: int,
    *,
    actor_id: int,
    is_admin: bool,
    client: Any,
    users: Any,
    subject: str | None = None,
    description: str | None = None,
    status_id: str | int | None = None,
    assigned_to_id: int | None = None,
    start_date: str | None = None,
    due_date: str | None = None,
    notes: str | None = None,
) -> dict:
    """Записать правку в Redmine по номеру и сразу прочитать только эту задачу."""
    _ensure(store)
    _guard(store, project_id, actor_id=actor_id, is_admin=is_admin)
    number = int(issue_id)
    card = _fields({
        "subject": subject,
        "description": description,
        "status_id": status_id,
        "assigned_to_id": assigned_to_id,
        "start_date": start_date,
        "due_date": due_date,
        "notes": notes,
    })
    try:
        client.update_issue(number, card)
    except (RedmineUnavailableError, *_DOWN) as exc:
        raise MirrorError("unavailable", "Redmine не ответил") from exc
    return {"updated": True, "issue": _pull(store, project_id, number, client, users)}


def connection_url(store: Any, project_id: int) -> str:
    """Адрес уже подключённого проекта. Ключ сюда не входит."""
    _ensure(store)
    row = _row(store, project_id)
    return str((row or {}).get("base_url") or "")


def run_due(
    store: Any, *, users: Any, now: datetime | None = None, client_factory: Any = None
) -> int:
    """Догрузить проекты, у которых с прошлой успешной копии прошло 15 минут.

    Возвращает, сколько проектов реально спрашивали у Redmine. Фабрика клиента
    получает только адрес. Без фабрики клиент берётся из ``REDMINE_API_KEY``.
    """
    from src.office.redmine_mirror._http import open_client

    _ensure(store)
    moment = _clock(now)
    factory = client_factory or open_client
    with store._lock:
        rows = store._connection().execute(
            "SELECT project_id, redmine_project, base_url, last_ok_at "
            "FROM office_redmine_mirrors WHERE connected = 1"
        ).fetchall()
    asked = 0
    for row in rows:
        last = row["last_ok_at"]
        if last:
            due = datetime.fromisoformat(last) + timedelta(minutes=SYNC_INTERVAL_MINUTES)
            if moment < due:
                continue
        try:
            client = factory(row["base_url"])
        except MirrorError:
            continue
        asked += 1
        try:
            load_project(
                store,
                int(row["project_id"]),
                actor_id=0,
                is_admin=True,
                client=client,
                users=users,
                redmine_project=row["redmine_project"],
                base_url=row["base_url"] or "",
                now=moment,
            )
        except MirrorError:
            continue
    return asked
