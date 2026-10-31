"""Граница tenancy: роли платформы и видимость проектов офиса.

Срез A: роли перечислены как в спецификации; создатель проекта записывается
его менеджером; администратор видит все проекты, остальные только те, где они
участники. Приглашений, настроек видимости, политики записи и ключей моделей
ещё нет. Публичные операции здесь, внутренности в модулях ``_*.py``.
"""
from src.office.tenancy._access import (
    can_create_project,
    can_decide,
    can_manage_validation,
    can_write,
    open_project,
    record_creator,
    visible_projects,
)
from src.office.tenancy._roles import CUSTOMER_ROLES, DECIDE_ROLES, MANAGER, ROLES

__all__ = [
    "CUSTOMER_ROLES",
    "DECIDE_ROLES",
    "MANAGER",
    "ROLES",
    "can_create_project",
    "can_decide",
    "can_manage_validation",
    "can_write",
    "open_project",
    "record_creator",
    "visible_projects",
]
