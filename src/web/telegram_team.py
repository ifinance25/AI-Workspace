"""Кого открывает Telegram вне белого списка (architecture/45).

Одно правило на виджет, ссылку ``/weblogin`` и бота. Результат всегда локальная
учётка: её права и отзыв работают как при входе по паролю.
"""
from __future__ import annotations

from typing import Any

CHANNEL_TELEGRAM = "telegram"


def resolve_team_account(
    telegram_id: int,
    *,
    allowed_user_ids,
    office_store: Any,
    session_manager: Any,
) -> dict[str, Any] | None:
    """Локальная учётка участника команды или None, если входить нельзя."""
    if office_store is None or session_manager is None:
        return None
    binding = office_store.find_active_binding(CHANNEL_TELEGRAM, str(telegram_id))
    if binding is None:
        return None
    user = session_manager.get_user_by_id(int(binding["user_id"]))
    if user is None or user.get("origin") != "local":
        return None
    if not user.get("is_active", 1) or user.get("is_admin"):
        return None
    # Старый локальный id мог совпасть с id из белого списка: такая сессия
    # получила бы все права оператора.
    if int(user["user_id"]) in set(allowed_user_ids or ()):
        return None
    return user
