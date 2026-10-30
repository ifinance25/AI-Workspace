"""Граница project: паспорт, тип маленький или крупный, вид работ, бриф, участники.

Публичные операции по спецификации: ``createProject`` (``create_project``) и
``setType`` (``set_type``). Текст предложения типа спрятан в ``suggest_type``.
Внутренности в модулях ``_*.py``.
"""
from src.office.project._passport import (
    NATURES,
    PAGE_LIMIT_MAX,
    WORK_KINDS,
    PassportError,
    create_project,
    list_projects,
)
from src.office.project._type import (
    TYPES,
    ProjectTypeError,
    TypeChangeForbiddenError,
    TypeLockedError,
    set_type,
    suggest_type,
)

__all__ = [
    "NATURES",
    "PAGE_LIMIT_MAX",
    "TYPES",
    "WORK_KINDS",
    "PassportError",
    "ProjectTypeError",
    "TypeChangeForbiddenError",
    "TypeLockedError",
    "create_project",
    "list_projects",
    "set_type",
    "suggest_type",
]
