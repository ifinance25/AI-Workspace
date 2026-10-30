"""Токен Redmine в админке. В ответ уходит только признак, что ключ сохранён."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.office import redmine_mirror
from src.web.dependencies import require_admin_factory


class _RedmineIn(BaseModel):
    base_url: str = ""
    redmine_project: str = ""
    api_key: str | None = None


def make_redmine_admin_router(
    *, jwt_secret: str, session_manager, office_store, allowed_user_ids=None
) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["admin"])
    require_admin = require_admin_factory(
        jwt_secret, session_manager, set(allowed_user_ids or [])
    )
    cipher = redmine_mirror.cipher_for(jwt_secret)

    @router.get("/redmine")
    async def get_redmine(_: dict = Depends(require_admin)) -> dict:
        return await asyncio.to_thread(redmine_mirror.account_view, office_store, cipher)

    @router.put("/redmine")
    async def put_redmine(body: _RedmineIn, _: dict = Depends(require_admin)) -> dict:
        return await asyncio.to_thread(
            redmine_mirror.save_account,
            office_store,
            cipher,
            base_url=body.base_url,
            redmine_project=body.redmine_project,
            api_key=body.api_key,
        )

    return router
