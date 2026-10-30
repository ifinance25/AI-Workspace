"""Внутренности tenancy: кто какой проект офиса видит."""
from __future__ import annotations

from src.office.storage import OfficeStore
from src.office.tenancy._roles import CUSTOMER_ROLES, MANAGER


def visible_projects(store: OfficeStore, *, actor_id: int, is_admin: bool) -> list[dict]:
    """Администратор видит все проекты, остальные только те, где они участники."""
    if is_admin:
        return store.list_projects()
    return store.list_projects_for_user(actor_id)


def open_project(
    store: OfficeStore, project_id: int, *, actor_id: int, is_admin: bool
) -> dict | None:
    """Проект, если он есть и открыт актору; иначе None.

    Чужой и несуществующий проект неразличимы: так нельзя перебором узнать,
    какие проекты существуют.
    """
    project = store.get_project(project_id)
    if project is None:
        return None
    if is_admin or store.get_member(project_id, actor_id) is not None:
        return project
    return None


def can_write(store: OfficeStore, project_id: int, *, actor_id: int, is_admin: bool) -> bool:
    """Можно ли актору менять документы проекта: участник не из ролей заказчика или АдмП.

    Проект считается уже открытым актору (``open_project``); здесь только роль.
    """
    if is_admin:
        return True
    member = store.get_member(project_id, actor_id)
    return member is not None and member["role"] not in CUSTOMER_ROLES


def can_create_project(store: OfficeStore, *, actor_id: int, is_admin: bool) -> bool:
    """Учётка, у которой все роли это роли заказчика, проектов не создаёт.

    Стороны учётки в срезе A нет (``03`` §8, миграция 0001), поэтому сторона
    читается по ролям: без ролей это новый сотрудник, ему можно.
    """
    if is_admin:
        return True
    roles = store.list_roles_for_user(actor_id)
    return not roles or any(role not in CUSTOMER_ROLES for role in roles)


def record_creator(store: OfficeStore, project_id: int, user_id: int) -> dict:
    """Создатель проекта записывается его менеджером."""
    return store.add_member(project_id, user_id, MANAGER)
