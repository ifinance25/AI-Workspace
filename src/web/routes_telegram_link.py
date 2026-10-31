"""Привязка Telegram к локальной учётке (architecture/11 §6.2, architecture/45).

Шаги: кнопка в настройках даёт одноразовую ссылку на бота, бот запоминает аккаунт,
владелец видит его в панели и подтверждает паролем. Пароль закрывает украденную
сессию: без него чужая вкладка закрепила бы за учёткой чужой Telegram навсегда.
"""
from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any, Callable

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from src.office.storage import ChannelBindingConflictError, hash_channel_code
from src.web.dependencies import get_current_user_factory
from src.web.passwords import verify_password
from src.web.rate_limit import LoginRateLimiter, client_key
from src.web.telegram_team import CHANNEL_TELEGRAM

logger = structlog.get_logger()

BIND_CODE_TTL_SECONDS = 10 * 60


class _ConfirmIn(BaseModel):
    password: str


def make_telegram_link_router(
    *,
    jwt_secret: str,
    session_manager: Any,
    office_store: Any,
    allowed_user_ids: list[int] | None,
    bot_username: str,
    is_bot_running: Callable[[], bool],
) -> APIRouter:
    router = APIRouter(prefix="/api/me/telegram", tags=["telegram-link"])
    get_current_user = get_current_user_factory(
        jwt_secret, session_manager, set(allowed_user_ids or [])
    )
    limiter = LoginRateLimiter()

    def _available() -> bool:
        return bool(bot_username) and is_bot_running()

    async def _local_account(user: dict[str, Any]) -> dict[str, Any]:
        row = await asyncio.to_thread(session_manager.get_user_by_id, int(user["user_id"]))
        if row is None or row.get("origin") != "local":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="local account required"
            )
        return row

    @router.get("")
    async def telegram_status(user: dict = Depends(get_current_user)) -> dict[str, Any]:
        row = await asyncio.to_thread(session_manager.get_user_by_id, int(user["user_id"]))
        local = row is not None and row.get("origin") == "local"
        binding = None
        if local:
            binding = await asyncio.to_thread(
                office_store.get_channel_binding, int(user["user_id"]), CHANNEL_TELEGRAM
            )
        if binding is None:
            state = "none"
        elif binding["state"] == "active":
            state = "active"
        elif binding["external_user_id"] is None:
            state = "waiting_start"
        else:
            state = "waiting_confirm"
        shown = binding if state in ("active", "waiting_confirm") else None
        return {
            "available": local and _available(),
            "state": state,
            "username": shown["external_username"] if shown else "",
            "external_user_id": shown["external_user_id"] if shown else "",
        }

    @router.post("/start")
    async def start_binding(user: dict = Depends(get_current_user)) -> dict[str, Any]:
        if not _available():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="telegram bot is not running"
            )
        row = await _local_account(user)
        user_id = int(row["user_id"])
        if await asyncio.to_thread(
            office_store.has_active_binding, user_id, CHANNEL_TELEGRAM
        ):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already bound")
        code = secrets.token_urlsafe(24)
        await asyncio.to_thread(
            office_store.start_channel_binding,
            user_id,
            CHANNEL_TELEGRAM,
            hash_channel_code(code),
            code_expires_at=time.time() + BIND_CODE_TTL_SECONDS,
        )
        return {
            "deep_link": f"https://t.me/{bot_username}?start=bind_{code}",
            "expires_in": BIND_CODE_TTL_SECONDS,
        }

    @router.post("/confirm")
    async def confirm_binding(
        payload: _ConfirmIn, request: Request, user: dict = Depends(get_current_user)
    ) -> dict[str, Any]:
        row = await _local_account(user)
        user_id = int(row["user_id"])
        key = client_key(request, f"telegram-link:{user_id}")
        retry = limiter.retry_after(key)
        if retry > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many attempts, try later",
                headers={"Retry-After": str(int(retry) + 1)},
            )
        if not row.get("password_hash") or not await asyncio.to_thread(
            verify_password, payload.password, row["password_hash"]
        ):
            limiter.record_failure(key)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
            )
        limiter.reset(key)
        try:
            binding = await asyncio.to_thread(
                office_store.confirm_channel_binding, user_id, CHANNEL_TELEGRAM
            )
        except ChannelBindingConflictError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="telegram already bound"
            )
        if binding is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="nothing to confirm"
            )
        # Вид из architecture/11 §6.2. Почтовый дубль придёт со срезом F.
        logger.info("access.channel_bound", user_id=user_id, channel=CHANNEL_TELEGRAM)
        return {"ok": True, "state": "active", "username": binding["external_username"]}

    @router.delete("")
    async def remove_binding(user: dict = Depends(get_current_user)) -> dict[str, Any]:
        row = await _local_account(user)
        user_id = int(row["user_id"])
        was_active = await asyncio.to_thread(
            office_store.has_active_binding, user_id, CHANNEL_TELEGRAM
        )
        removed = await asyncio.to_thread(
            office_store.revoke_channel_binding, user_id, CHANNEL_TELEGRAM
        )
        if was_active:
            # JWT живёт дни: сессии, открытые через этот Telegram, гаснут сразу.
            # Отмена незавершённой попытки сессий не касается.
            await asyncio.to_thread(session_manager.bump_token_version, user_id)
            logger.info("access.channel_unbound", user_id=user_id, channel=CHANNEL_TELEGRAM)
        return {"ok": True, "removed": removed}

    return router
