"""Состав команды проекта: кто в нём и в какой роли.

Роль выдаёт менеджер проекта или администратор. Учётку создаёт администратор
(``/api/admin/users``), здесь она только входит в проект. Администратор
системы остаётся флагом учётки: роли ``system_admin`` участнику не даются.
"""
from __future__ import annotations

from src.office.storage import OfficeStore
from src.office.tenancy._roles import MANAGER, ROLES


class MembersError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


ASSIGNABLE = {key: label for key, label in ROLES.items() if key != "system_admin"}


def check_role(role: str) -> str:
    if role not in ASSIGNABLE:
        raise MembersError("bad_input", "Такой роли нет")
    return role


def list_team(store: OfficeStore, project_id: int) -> list[dict]:
    """Участники проекта: ``user_id``, ``role``, ``added_at``."""
    return [
        {"user_id": m["user_id"], "role": m["role"], "added_at": m["added_at"]}
        for m in store.list_members(project_id)
    ]


def add_or_set(store: OfficeStore, project_id: int, user_id: int, role: str) -> dict:
    """Добавляет участника или меняет ему роль; последнего менеджера не сменить."""
    check_role(role)
    if store.get_member(project_id, user_id) is None:
        member = store.add_member(project_id, user_id, role)
        return {"user_id": member["user_id"], "role": member["role"]}
    if not store.change_member(project_id, user_id, role, manager_role=MANAGER):
        raise MembersError("last_manager", "В проекте должен остаться менеджер проекта")
    return {"user_id": user_id, "role": role}


def remove_member(store: OfficeStore, project_id: int, user_id: int) -> None:
    if store.get_member(project_id, user_id) is None:
        raise MembersError("not_found", "Участник не найден")
    if not store.change_member(project_id, user_id, None, manager_role=MANAGER):
        raise MembersError("last_manager", "В проекте должен остаться менеджер проекта")
