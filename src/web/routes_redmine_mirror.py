"""Зеркало Redmine: четыре вызова под ``/api/office``.

Ключ берётся из ``REDMINE_API_KEY`` в момент обращения и в ответ не кладётся.
Расписание 15 минут догружает уже подключённые проекты.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.office import redmine_mirror

log = structlog.get_logger()

_STATUS = {
    "not_found": 404,
    "customer": 403,
    "unavailable": 503,
    "no_number": 502,
    "no_key": 503,
    "pending": 409,
}


class _SyncIn(BaseModel):
    redmine_project: str
    base_url: str = ""


class _CreateIn(BaseModel):
    request_key: str
    redmine_project: str
    subject: str
    description: str = ""
    status_id: str | int | None = None
    assigned_to_id: int | None = None
    start_date: str | None = None
    due_date: str | None = None
    notes: str | None = None
    base_url: str = ""


class _UpdateIn(BaseModel):
    subject: str | None = None
    description: str | None = None
    status_id: str | int | None = None
    assigned_to_id: int | None = None
    start_date: str | None = None
    due_date: str | None = None
    notes: str | None = None
    base_url: str = ""


class _LazyClient:
    """Клиент открывается на первом вызове, чтобы отказ по правам не трогал ключ."""

    def __init__(self, base_url: str):
        self._base_url = base_url
        self._real = None

    def _client(self):
        if self._real is None:
            self._real = redmine_mirror.open_client(self._base_url)
        return self._real

    def list_issues(self, project: str) -> list[dict]:
        return self._client().list_issues(project)

    def get_issue(self, issue_id: int) -> dict:
        return self._client().get_issue(issue_id)

    def create_issue(self, project: str, fields: dict) -> dict:
        return self._client().create_issue(project, fields)

    def update_issue(self, issue_id: int, fields: dict) -> None:
        self._client().update_issue(issue_id, fields)

    def get_user(self, user_id: int) -> dict:
        return self._client().get_user(user_id)


def make_redmine_mirror_router(
    *, office_store, require_actor, require_project, session_manager
) -> APIRouter:
    async def _schedule() -> None:
        while True:
            try:
                await asyncio.to_thread(
                    redmine_mirror.run_due, office_store, users=session_manager
                )
            except Exception as exc:
                log.warning("redmine_mirror_schedule_failed", error=type(exc).__name__)
            await asyncio.sleep(redmine_mirror.SYNC_INTERVAL_MINUTES * 60)

    @asynccontextmanager
    async def _lifespan(_app):
        job = asyncio.create_task(_schedule())
        try:
            yield
        finally:
            job.cancel()
            with suppress(asyncio.CancelledError):
                await job

    router = APIRouter(tags=["redmine-mirror"], lifespan=_lifespan)

    def _fail(exc: redmine_mirror.MirrorError) -> HTTPException:
        return HTTPException(status_code=_STATUS.get(exc.code, 502), detail=exc.message)

    def _url(project_id: int, base_url: str) -> str:
        return base_url or redmine_mirror.connection_url(office_store, project_id)

    @router.post("/projects/{project_id}/redmine/load")
    async def load_project(body: _SyncIn, ctx: dict = Depends(require_project)) -> dict:
        try:
            return await asyncio.to_thread(
                redmine_mirror.load_project,
                office_store,
                ctx["project"]["id"],
                actor_id=ctx["actor"]["user_id"],
                is_admin=ctx["actor"]["is_admin"],
                client=_LazyClient(_url(ctx["project"]["id"], body.base_url)),
                users=session_manager,
                redmine_project=body.redmine_project,
                base_url=body.base_url,
            )
        except redmine_mirror.MirrorError as exc:
            raise _fail(exc) from exc

    @router.post("/projects/{project_id}/redmine/issues/{issue_id}/load")
    async def load_issue(
        issue_id: int, body: _UpdateIn, ctx: dict = Depends(require_project)
    ) -> dict:
        try:
            return await asyncio.to_thread(
                redmine_mirror.load_issue,
                office_store,
                ctx["project"]["id"],
                issue_id,
                actor_id=ctx["actor"]["user_id"],
                is_admin=ctx["actor"]["is_admin"],
                client=_LazyClient(_url(ctx["project"]["id"], body.base_url)),
                users=session_manager,
            )
        except redmine_mirror.MirrorError as exc:
            raise _fail(exc) from exc

    @router.post("/projects/{project_id}/redmine/issues")
    async def create_issue(body: _CreateIn, ctx: dict = Depends(require_project)) -> dict:
        try:
            return await asyncio.to_thread(
                redmine_mirror.create_issue,
                office_store,
                ctx["project"]["id"],
                actor_id=ctx["actor"]["user_id"],
                is_admin=ctx["actor"]["is_admin"],
                client=_LazyClient(_url(ctx["project"]["id"], body.base_url)),
                users=session_manager,
                request_key=body.request_key,
                redmine_project=body.redmine_project,
                subject=body.subject,
                description=body.description,
                status_id=body.status_id,
                assigned_to_id=body.assigned_to_id,
                start_date=body.start_date,
                due_date=body.due_date,
                notes=body.notes,
                base_url=body.base_url,
            )
        except redmine_mirror.MirrorError as exc:
            raise _fail(exc) from exc

    @router.put("/projects/{project_id}/redmine/issues/{issue_id}")
    async def update_issue(
        issue_id: int, body: _UpdateIn, ctx: dict = Depends(require_project)
    ) -> dict:
        try:
            return await asyncio.to_thread(
                redmine_mirror.update_issue,
                office_store,
                ctx["project"]["id"],
                issue_id,
                actor_id=ctx["actor"]["user_id"],
                is_admin=ctx["actor"]["is_admin"],
                client=_LazyClient(_url(ctx["project"]["id"], body.base_url)),
                users=session_manager,
                subject=body.subject,
                description=body.description,
                status_id=body.status_id,
                assigned_to_id=body.assigned_to_id,
                start_date=body.start_date,
                due_date=body.due_date,
                notes=body.notes,
            )
        except redmine_mirror.MirrorError as exc:
            raise _fail(exc) from exc

    # require_actor нужен фабрике офиса, как у соседних роутеров. Проверку
    # проекта делает require_project, заказчика отсекает само зеркало.
    del require_actor
    return router
