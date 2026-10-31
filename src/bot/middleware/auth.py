"""Authentication middleware."""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.dispatcher.flags import get_flag
from aiogram.types import CallbackQuery, Message, TelegramObject

import structlog

logger = structlog.get_logger()


# Флаги обработчиков, доступных вне белого списка (src/bot/handlers/commands.py).
FLAG_TELEGRAM_BIND = "telegram_bind"
FLAG_TEAM_WEBLOGIN = "team_weblogin"


class AuthMiddleware(BaseMiddleware):
    """Middleware to check user authorization."""

    def __init__(
        self,
        allowed_user_ids: list[int],
        session_manager: Any = None,
        team_resolver: Callable[[int], dict[str, Any] | None] | None = None,
    ):
        self.allowed_user_ids = set(allowed_user_ids)
        # Находит локальную учётку участника команды по telegram id.
        self.team_resolver = team_resolver
        # H-1/M-10: апсертим строку users (+username) при взаимодействии с ботом,
        # чтобы приглашение по @username / числовому id резолвилось. In-memory
        # кэш гасит повторные записи (одна на (id, username) за жизнь процесса).
        self.session_manager = session_manager
        self._recorded: set[tuple[int, str | None]] = set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Get user from event
        user = None
        if isinstance(event, Message) and event.from_user:
            user = event.from_user
        elif isinstance(event, CallbackQuery) and event.from_user:
            user = event.from_user

        # Allow if user is in whitelist
        if user and user.id in self.allowed_user_ids:
            logger.debug(
                "auth_ok",
                user_id=user.id,
                username=user.username,
            )
            await self._record_user(user.id, user.username)
            return await handler(event, data)

        if user and isinstance(event, Message) and await self._allowed_outside_whitelist(
            event, user.id, data
        ):
            return await handler(event, data)

        # Log unauthorized access attempt
        if user:
            logger.warning(
                "⛔ unauthorized_access",
                user_id=user.id,
                username=user.username,
                name=user.full_name,
            )

        # Silently ignore unauthorized users
        return None

    async def _allowed_outside_whitelist(
        self, message: Message, user_id: int, data: dict[str, Any]
    ) -> bool:
        """Только личный чат: шаг привязки и точная команда /weblogin участника.

        Остальное для участника команды закрыто: Claude из бота только у белого
        списка. Строку ``users`` здесь не пишем, id Telegram не становится учёткой.
        """
        if message.chat.type != "private":
            return False
        if get_flag(data, FLAG_TELEGRAM_BIND):
            return True
        if not get_flag(data, FLAG_TEAM_WEBLOGIN) or message.text != "/weblogin":
            return False
        if self.team_resolver is None:
            return False
        return await asyncio.to_thread(self.team_resolver, user_id) is not None

    async def _record_user(self, user_id: int, username: str | None) -> None:
        """Апсерт users-строки (H-1/M-10). Никогда не мешает обработке события."""
        if self.session_manager is None:
            return
        key = (user_id, username)
        if key in self._recorded:
            return
        self._recorded.add(key)
        try:
            await asyncio.to_thread(
                self.session_manager.record_telegram_user, user_id, username
            )
        except Exception as exc:  # noqa: BLE001 — запись не должна ронять хендлер
            self._recorded.discard(key)
            logger.debug("record_telegram_user_failed", user_id=user_id, error=str(exc))
