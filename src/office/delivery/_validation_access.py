"""Права валидации. Отдельно от ``can_write``: та шире, чем 10 §16."""
from __future__ import annotations

from typing import Any

from src.office import tenancy
from src.office.delivery._validation_schema import ValidationError


def require_team(store: Any, project_id: int, *, actor_id: int, is_admin: bool) -> None:
    """Заказчик ничего из валидации не открывает (И-13, 10 §16)."""
    member = store.get_member(project_id, actor_id)
    if member is not None and member["role"] in tenancy.CUSTOMER_ROLES:
        raise ValidationError("customer", "Раздел закрыт для заказчика")
    if tenancy.open_project(store, project_id, actor_id=actor_id, is_admin=is_admin) is None:
        raise ValidationError("not_found", "Проект не найден")


def require_decide(store: Any, project_id: int, *, actor_id: int, is_admin: bool) -> str:
    """Роль автора решения. Журнал хранит роль, поэтому роль нужна и администратору."""
    if not tenancy.can_decide(store, project_id, actor_id=actor_id, is_admin=is_admin):
        raise ValidationError("forbidden", "Статус ставят МП, тестировщик, БА и СА проекта")
    return store.get_member(project_id, actor_id)["role"]


def require_manage(store: Any, project_id: int, *, actor_id: int, is_admin: bool) -> None:
    if not tenancy.can_manage_validation(
        store, project_id, actor_id=actor_id, is_admin=is_admin
    ):
        raise ValidationError("forbidden", "Действие доступно менеджеру проекта и администратору")
