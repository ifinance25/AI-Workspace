"""Внутренности project: проверка паспорта и создание проекта."""
from __future__ import annotations

from src.office import tenancy
from src.office.project._type import ACTIVE, check_type
from src.office.storage import OfficeStore

WORK_KINDS = {
    "site": "Сайт",
    "web_platform": "Веб-платформа",
    "mobile_app": "Мобильное приложение",
}
NATURES = {"custom": "Заказ", "product": "Продукт"}


class PassportError(ValueError):
    """Паспорт заполнен неверно; текст ошибки показывается человеку."""


def _clean_passport(passport: dict) -> dict:
    name = str(passport.get("name") or "").strip()
    work_kind = str(passport.get("work_kind") or "")
    nature = str(passport.get("nature") or "")
    if not name:
        raise PassportError("Укажите название проекта")
    if work_kind not in WORK_KINDS:
        raise PassportError("Выберите вид работ: сайт, веб-платформа или мобильное приложение")
    if nature not in NATURES:
        raise PassportError("Выберите характер: заказ или продукт")
    return {
        "name": name,
        "work_kind": work_kind,
        "nature": nature,
        "description": str(passport.get("description") or "").strip(),
    }


def create_project(store: OfficeStore, passport: dict, *, actor_id: int) -> dict:
    """createProject: паспорт проекта; создатель записан менеджером."""
    fields = _clean_passport(passport)
    project_type = str(passport.get("project_type") or "")
    if project_type:
        # Тип выбран в мастере: проект стартует сразу.
        fields.update(project_type=check_type(project_type), status=ACTIVE)
    # Ключ идемпотентности с клиента: двойное «Создать» даёт один проект.
    request_key = str(passport.get("request_key") or "").strip()[:100] or None
    project = store.create_project(created_by=actor_id, create_key=request_key, **fields)
    tenancy.record_creator(store, project["id"], actor_id)
    return project


PAGE_LIMIT_MAX = 200


def list_projects(
    store: OfficeStore, *, actor_id: int, is_admin: bool, offset: int = 0, limit: int = 50,
) -> list[dict]:
    """Страница видимых актору проектов: список листается, не отдаётся целиком."""
    visible = tenancy.visible_projects(store, actor_id=actor_id, is_admin=is_admin)
    return visible[offset:offset + limit]
