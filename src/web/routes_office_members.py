"""Состав команды проекта офиса под ``/api/office``.

Смотрят все члены команды, кроме сторон заказчика. Роль выдаёт менеджер проекта
или администратор. Учётку создаёт администратор, здесь она входит в проект по
логину. Логины и роли в журнал приложения не пишутся.
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.office import tenancy

_STATUS = {"bad_input": 422, "last_manager": 409, "not_found": 404}


class _MemberIn(BaseModel):
    username: str
    role: str


class _RoleIn(BaseModel):
    role: str


def _fail(exc: tenancy.MembersError) -> HTTPException:
    return HTTPException(status_code=_STATUS.get(exc.code, 422), detail=exc.message)


def make_office_members_router(
    *, office_store: Any, require_project: Any, session_manager: Any,
) -> APIRouter:
    async def require_team(ctx: dict = Depends(require_project)) -> dict:
        actor = ctx["actor"]
        allowed = await asyncio.to_thread(
            tenancy.can_write, office_store, ctx["project"]["id"],
            actor_id=actor["user_id"], is_admin=actor["is_admin"],
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Раздел недоступен для вашей роли")
        return ctx

    async def require_manage(ctx: dict = Depends(require_team)) -> dict:
        actor = ctx["actor"]
        allowed = await asyncio.to_thread(
            tenancy.can_manage_team, office_store, ctx["project"]["id"],
            actor_id=actor["user_id"], is_admin=actor["is_admin"],
        )
        if not allowed:
            raise HTTPException(status_code=403, detail="Состав команды меняет менеджер проекта")
        return ctx

    router = APIRouter(
        prefix="/projects/{project_id}/members",
        tags=["office-members"],
        dependencies=[Depends(require_team)],
    )

    def _named(rows: list[dict]) -> list[dict]:
        out = []
        for row in rows:
            user = session_manager.get_user_by_id(row["user_id"])
            out.append({
                **row,
                "username": (user or {}).get("username") or f"№{row['user_id']}",
                "label": tenancy.ROLES.get(row["role"], row["role"]),
            })
        return out

    @router.get("")
    async def team(ctx: dict = Depends(require_team)) -> dict:
        project_id, actor = ctx["project"]["id"], ctx["actor"]
        rows = await asyncio.to_thread(tenancy.list_team, office_store, project_id)
        can_manage = await asyncio.to_thread(
            tenancy.can_manage_team, office_store, project_id,
            actor_id=actor["user_id"], is_admin=actor["is_admin"],
        )
        return {
            "members": await asyncio.to_thread(_named, rows),
            "can_manage": can_manage,
            "roles": [{"key": k, "label": v} for k, v in tenancy.ASSIGNABLE.items()],
        }

    @router.post("", status_code=201)
    async def add(body: _MemberIn, ctx: dict = Depends(require_manage)) -> dict:
        user = await asyncio.to_thread(
            session_manager.get_user_by_username, body.username.strip().lstrip("@"),
        )
        if user is None or not user.get("is_active", True):
            raise HTTPException(
                status_code=404,
                detail="Учётка не найдена. Её создаёт администратор в разделе «Администрирование».",
            )
        try:
            return await asyncio.to_thread(
                tenancy.add_or_set, office_store, ctx["project"]["id"],
                int(user["user_id"]), body.role,
            )
        except tenancy.MembersError as exc:
            raise _fail(exc) from exc

    @router.put("/{user_id}")
    async def set_role(user_id: int, body: _RoleIn, ctx: dict = Depends(require_manage)) -> dict:
        project_id = ctx["project"]["id"]
        if await asyncio.to_thread(office_store.get_member, project_id, user_id) is None:
            raise HTTPException(status_code=404, detail="Участник не найден")
        try:
            return await asyncio.to_thread(
                tenancy.add_or_set, office_store, project_id, user_id, body.role,
            )
        except tenancy.MembersError as exc:
            raise _fail(exc) from exc

    @router.delete("/{user_id}", status_code=204)
    async def remove(user_id: int, ctx: dict = Depends(require_manage)) -> None:
        try:
            await asyncio.to_thread(
                tenancy.remove_member, office_store, ctx["project"]["id"], user_id,
            )
        except tenancy.MembersError as exc:
            raise _fail(exc) from exc

    return router
