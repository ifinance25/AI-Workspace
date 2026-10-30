"""Внутренности project: тип проекта, его предложение и смена."""
from __future__ import annotations

from src.office import tenancy
from src.office.storage import OfficeStore

TYPES = {"small": "Маленький", "large": "Крупный"}

DRAFT = "draft"
ACTIVE = "active"

# Статус принятой заказчиком версии задания. Автомат статусов живёт в cycle
# (таск 04); project только читает версии, флага «тип заморожен» нет.
SPEC_KIND = "spec"
SPEC_ACCEPTED = "accepted"


class ProjectTypeError(ValueError):
    """Неизвестный тип проекта."""


class TypeLockedError(ProjectTypeError):
    """Тип не меняется: заказчик уже принял версию задания."""


class TypeChangeForbiddenError(PermissionError):
    """Тип меняют только менеджер проекта и администратор."""


def suggest_type(*, work_kind: str, nature: str, description: str = "") -> dict:
    """Предложение типа и одна фраза почему. Выбор остаётся за менеджером."""
    if nature == "product":
        return {
            "project_type": "large",
            "reason": "Продукт живёт дольше одного заказа, поэтому ему нужны оценки, "
                      "бюджет и график.",
        }
    if work_kind in ("web_platform", "mobile_app"):
        what = "Веб-платформа" if work_kind == "web_platform" else "Мобильное приложение"
        return {
            "project_type": "large",
            "reason": f"{what} на заказ обычно требует дерева работ, оценок и графика.",
        }
    return {
        "project_type": "small",
        "reason": "Сайт на заказ укладывается в паспорт, бриф и задачи без бюджета и графика.",
    }


def check_type(project_type: str) -> str:
    if project_type not in TYPES:
        raise ProjectTypeError("Тип проекта: маленький или крупный")
    return project_type


def _spec_accepted(store: OfficeStore, project_id: int) -> bool:
    document = store.get_document(project_id, SPEC_KIND)
    if document is None:
        return False
    return any(v["status"] == SPEC_ACCEPTED for v in store.list_versions(document["id"]))


def set_type(
    store: OfficeStore, project_id: int, project_type: str, *, actor_id: int, is_admin: bool,
) -> dict:
    """setType: выбранный тип запускает проект из черновика.

    Менять можно, пока ни одна версия задания не принята заказчиком.
    """
    check_type(project_type)
    project = store.get_project(project_id)
    if project is None:
        raise LookupError(project_id)
    member = store.get_member(project_id, actor_id)
    if not is_admin and (member is None or member["role"] != tenancy.MANAGER):
        raise TypeChangeForbiddenError("Тип проекта выбирает менеджер проекта")
    if _spec_accepted(store, project_id):
        raise TypeLockedError("Тип нельзя сменить: заказчик уже принял версию задания")
    fields = {"project_type": project_type}
    if project["status"] == DRAFT:
        fields["status"] = ACTIVE
    updated = store.update_project(project_id, **fields)
    assert updated is not None
    return updated
