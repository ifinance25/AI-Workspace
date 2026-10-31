"""Роли платформы, как в таблице ролей раздела «Решение» спецификации.

Ключ хранится в ``office_members.role``, значение показывается в интерфейсе.
Администратор системы определяется флагом аккаунта (``users.is_admin``),
а не записью участника: он открывает любой проект без членства.
"""
from __future__ import annotations

MANAGER = "project_manager"

# Роли стороны заказчика: читают по видимости, не пишут документы проекта и не
# создают проекты (У43-09; `03` §5.2, §5.3). Полная матрица 12 ролей это срез B.
CUSTOMER_ROLES = frozenset({"customer_representative", "customer_signatory"})

# Кто ставит статус находке прогона (`10` §16).
DECIDE_ROLES = frozenset({MANAGER, "tester", "business_analyst", "system_analyst"})

ROLES: dict[str, str] = {
    MANAGER: "Менеджер проекта",
    "pmo_head": "Руководитель проектного офиса",
    "observer": "Наблюдатель",
    "business_analyst": "Бизнес-аналитик",
    "system_analyst": "Системный аналитик",
    "architect": "Архитектор",
    "developer": "Разработчик",
    "tester": "Тестировщик",
    "customer_representative": "Представитель заказчика",
    "customer_signatory": "Подписант со стороны заказчика",
    "system_admin": "Администратор системы",
}
