"""Проектный офис: общие зависимости авторизации и монтирование роутеров границ.

Маршруты ``/api/office/...``. Видимость проекта решает ``tenancy``: администратор
видит все проекты, остальные только те, где они участники. Чужой и
несуществующий проект отдают 404 (как ``require_owned_session`` у сессий).
Роутеры паспорта, брифа и задания получают отсюда ``require_actor`` и
``require_project`` и не повторяют проверку доступа.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.office import redmine_mirror, tenancy
from src.web.dependencies import get_current_user_factory
from src.web.routes_office_brief import make_office_brief_router
from src.web.routes_office_project import make_office_project_router
from src.web.routes_office_spec import make_office_spec_router
from src.web.routes_office_validation import make_validation_router
from src.web.routes_redmine_mirror import make_redmine_mirror_router


def make_office_router(
    *,
    jwt_secret: str,
    session_manager,
    office_store,
    allowed_user_ids=None,
    connections_secret_key: str = "",
) -> APIRouter:
    router = APIRouter(prefix="/api/office", tags=["office"])
    get_current_user = get_current_user_factory(jwt_secret, session_manager, allowed_user_ids)

    async def require_actor(
        user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        """``{user_id, is_admin}``: роль перепроверяется по БД, как в ``require_admin``."""
        uid = int(user["user_id"])
        is_admin = bool(user.get("is_admin"))
        row = await asyncio.to_thread(session_manager.get_user_by_id, uid)
        if row is not None:
            is_admin = bool(row.get("is_admin"))
        return {"user_id": uid, "is_admin": is_admin}

    async def require_project(
        project_id: int, actor: dict[str, Any] = Depends(require_actor),
    ) -> dict[str, Any]:
        """``{actor, project}`` для проекта, открытого актору; 404 иначе."""
        project = await asyncio.to_thread(
            tenancy.open_project, office_store, project_id,
            actor_id=actor["user_id"], is_admin=actor["is_admin"],
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Проект не найден")
        return {"actor": actor, "project": project}

    for make_sub_router in (
        make_office_project_router, make_office_brief_router, make_office_spec_router,
    ):
        router.include_router(
            make_sub_router(
                office_store=office_store,
                require_actor=require_actor,
                require_project=require_project,
            )
        )
    router.include_router(
        make_redmine_mirror_router(
            office_store=office_store,
            require_actor=require_actor,
            require_project=require_project,
            session_manager=session_manager,
            cipher=redmine_mirror.cipher_from_key(connections_secret_key),
            proposal_secret=jwt_secret,
        )
    )
    router.include_router(
        make_validation_router(
            office_store=office_store,
            require_project=require_project,
            session_manager=session_manager,
        )
    )
    return router
