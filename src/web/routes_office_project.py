"""Паспорт проекта офиса: роутер границы ``project``.

Пути относительно ``/api/office`` (префикс добавляет ``routes_office``).
Список проектов и проект по id живут здесь же, чтобы паспорт был в одном файле.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.office import delivery, tenancy
from src.office import project as office_project


class PassportIn(BaseModel):
    name: str = ""
    work_kind: str = ""
    nature: str = ""
    description: str = ""
    project_type: str = ""
    request_key: str = ""


class SuggestIn(BaseModel):
    work_kind: str = ""
    nature: str = ""
    description: str = ""


class TypeIn(BaseModel):
    project_type: str


class PassportPatchIn(BaseModel):
    name: str | None = None
    work_kind: str | None = None
    nature: str | None = None
    description: str | None = None


def make_office_project_router(*, office_store, require_actor, require_project) -> APIRouter:
    router = APIRouter(tags=["office-project"])

    @router.get("/projects")
    async def list_projects(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=office_project.PAGE_LIMIT_MAX),
        actor: dict[str, Any] = Depends(require_actor),
    ) -> list[dict]:
        """Страница проектов, открытых актору; «показать ещё» просит следующую."""
        return await asyncio.to_thread(
            office_project.list_projects, office_store,
            actor_id=actor["user_id"], is_admin=actor["is_admin"],
            offset=offset, limit=limit,
        )

    @router.post("/projects", status_code=201)
    async def create_project(
        body: PassportIn, actor: dict[str, Any] = Depends(require_actor),
    ) -> dict:
        # У43-09: учётка только с ролями заказчика проектов не создаёт (`03` §5.2).
        allowed = await asyncio.to_thread(
            tenancy.can_create_project,
            office_store,
            actor_id=actor["user_id"],
            is_admin=actor["is_admin"],
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Учётка заказчика не создаёт проекты")
        try:
            return await asyncio.to_thread(
                office_project.create_project, office_store, body.model_dump(),
                actor_id=actor["user_id"],
            )
        except (office_project.PassportError, office_project.ProjectTypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post("/type-suggestion")
    async def suggest_type(
        body: SuggestIn, actor: dict[str, Any] = Depends(require_actor),
    ) -> dict:
        return office_project.suggest_type(**body.model_dump())

    @router.get("/projects/{project_id}")
    async def get_project(ctx: dict[str, Any] = Depends(require_project)) -> dict:
        return ctx["project"]

    @router.put("/projects/{project_id}")
    async def update_project(
        body: PassportPatchIn,
        ctx: dict[str, Any] = Depends(require_project),
    ) -> dict:
        actor = ctx["actor"]
        patch = body.model_dump(exclude_unset=True)
        try:
            return await asyncio.to_thread(
                office_project.update_passport,
                office_store,
                ctx["project"]["id"],
                patch,
                actor_id=actor["user_id"],
                is_admin=actor["is_admin"],
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="Недостаточно прав") from exc
        except LookupError as exc:
            if str(exc) == "project_not_found":
                raise HTTPException(status_code=404, detail="Проект не найден") from exc
            raise
        except office_project.PassportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete("/projects/{project_id}", status_code=204)
    async def delete_project(ctx: dict[str, Any] = Depends(require_project)) -> None:
        actor = ctx["actor"]
        project_id = ctx["project"]["id"]
        has_validation = await asyncio.to_thread(delivery.has_runs, office_store, project_id)
        if has_validation and not tenancy.can_manage_validation(
            office_store, project_id, actor_id=actor["user_id"], is_admin=actor["is_admin"]
        ):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        try:
            await asyncio.to_thread(
                office_project.delete_project,
                office_store,
                ctx["project"]["id"],
                actor_id=actor["user_id"],
                is_admin=actor["is_admin"],
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail="Недостаточно прав") from exc
        except LookupError as exc:
            if str(exc) == "project_not_found":
                raise HTTPException(status_code=404, detail="Проект не найден") from exc
            raise
        await asyncio.to_thread(delivery.purge_project_files, office_store, project_id)

    @router.put("/projects/{project_id}/type")
    async def set_type(
        body: TypeIn, ctx: dict[str, Any] = Depends(require_project),
    ) -> dict:
        actor = ctx["actor"]
        try:
            return await asyncio.to_thread(
                office_project.set_type, office_store, ctx["project"]["id"], body.project_type,
                actor_id=actor["user_id"], is_admin=actor["is_admin"],
            )
        except office_project.TypeChangeForbiddenError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except office_project.TypeLockedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except office_project.ProjectTypeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return router
