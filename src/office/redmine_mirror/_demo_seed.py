"""Демо-задачи зеркала Redmine для локального стенда без API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.office.redmine_mirror._mirror import _ensure, _mark, _save

_DEMO_REDMINE_PROJECT = "demo-local"


def is_demo_mirror(store: Any, project_id: int, redmine_project: str) -> bool:
    row = store._connection().execute(
        "SELECT redmine_project, connected FROM office_redmine_mirrors WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if not row or not row["connected"]:
        return False
    project = (redmine_project or row["redmine_project"] or "").strip()
    return project == _DEMO_REDMINE_PROJECT


def _next_issue_id(conn: Any, project_id: int) -> int:
    found = conn.execute(
        "SELECT COALESCE(MAX(issue_id), 100) FROM office_redmine_issues WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return int(found[0]) + 1


def create_demo_issue(
    store: Any,
    project_id: int,
    *,
    subject: str,
    description: str = "",
    status_id: str | None = None,
    status_name: str | None = None,
    assigned_to_id: int | None = None,
) -> dict:
    """Локальное создание задачи для demo-local без Redmine API."""
    _ensure(store)
    sid = status_id or "1"
    sname = status_name or "Новая"
    assignee = (
        _person(assigned_to_id, f"user{assigned_to_id}", f"Пользователь {assigned_to_id}")
        if assigned_to_id
        else {"user_id": None, "login": "", "name": ""}
    )
    with store._lock:
        conn = store._connection()
        issue_id = _next_issue_id(conn, project_id)
        issue = _issue(
            issue_id,
            subject.strip() or "Без темы",
            sname,
            sid,
            assignee=assignee,
            author=_person(3, "ivan", "Иван Петров"),
        )
        issue["description"] = description
        _save(conn, project_id, issue)
        conn.commit()
    return issue


def _person(user_id: int, login: str, name: str) -> dict:
    return {"user_id": user_id, "login": login, "name": name}


def _issue(
    issue_id: int,
    subject: str,
    status_name: str,
    status_id: str,
    *,
    assignee: dict | None = None,
    author: dict | None = None,
    ftt_section: str = "База знаний",
    cycle_hours: float | None = None,
    issue_type: str = "Задача",
    environment: str = "Прод",
    due_date: str | None = "2026-11-15",
) -> dict:
    author = author or _person(3, "ivan", "Иван Петров")
    assignee = assignee or _person(4, "anna", "Анна Смирнова")
    return {
        "id": issue_id,
        "subject": subject,
        "description": f"Демо: {subject}",
        "status": {"id": status_id, "name": status_name},
        "author": author,
        "assignee": assignee,
        "start_date": "2026-10-01",
        "due_date": due_date,
        "comments": [],
        "status_history": [],
        "assignee_history": [],
        "ftt_section": ftt_section,
        "cycle_hours": cycle_hours,
        "type": issue_type,
        "environment": environment,
    }


DEMO_ISSUES: list[dict] = [
    _issue(101, "Паспорт проекта", "Новая", "1", assignee={"user_id": None, "login": "", "name": ""}),
    _issue(102, "Согласовать бриф", "Новая", "1", assignee=_person(5, "olga", "Ольга К.")),
    _issue(103, "Вёрстка лендинга", "В работе", "2"),
    _issue(104, "Интеграция оплаты", "В работе", "2", assignee=_person(8, "boris", "Борис М.")),
    _issue(105, "Ревью API", "На проверке", "3", cycle_hours=4.5),
    _issue(106, "Тесты регресса", "На проверке", "3", assignee=_person(8, "boris", "Борис М.")),
    _issue(
        107,
        "Статья в базе знаний",
        "Закрыта",
        "5",
        ftt_section="База знаний",
        cycle_hours=12,
    ),
    _issue(
        108,
        "Курс в LMS",
        "Закрыта",
        "5",
        ftt_section="Управление электронным обучением",
        assignee=_person(4, "anna", "Анна Смирнова"),
        cycle_hours=6,
    ),
    _issue(109, "Макет главной", "В работе", "2", issue_type="Ошибка", environment="Тест"),
    _issue(110, "Доступ заказчика", "Новая", "1", environment="Тест"),
]


def seed_demo_mirror(store: Any, project_id: int) -> int:
    """Записать демо-задачи в зеркало. Redmine API не вызывается."""
    _ensure(store)
    moment = datetime.now(timezone.utc)
    with store._lock:
        conn = store._connection()
        conn.execute("DELETE FROM office_redmine_issues WHERE project_id = ?", (project_id,))
        for row in DEMO_ISSUES:
            _save(conn, project_id, row)
        _mark(
            conn,
            project_id,
            redmine_project=_DEMO_REDMINE_PROJECT,
            base_url="http://127.0.0.1",
            moment=moment,
        )
        conn.commit()
    return len(DEMO_ISSUES)
