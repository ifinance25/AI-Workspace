"""Зеркало Redmine: четыре вызова под ``/api/office``.

Ключ берётся из сохранённой учётки (шифр ``CONNECTIONS_SECRET_KEY``) или из
``REDMINE_API_KEY`` в момент обращения и в ответ не кладётся.
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
    "bad_url": 503,
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

    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url
        self._api_key = api_key
        self._real = None

    def _client(self):
        if self._real is None:
            if not self._api_key:
                raise redmine_mirror.MirrorError("no_key", "Ключ Redmine не задан")
            from src.office.redmine_mirror._http import HttpRedmine

            self._real = HttpRedmine(self._base_url, self._api_key)
        return self._real

    def list_issues(self, project: str, **kwargs) -> list[dict]:
        return self._client().list_issues(project, **kwargs)

    def list_issue_ids(self, project: str) -> set[int]:
        return self._client().list_issue_ids(project)

    def get_issue(self, issue_id: int) -> dict:
        return self._client().get_issue(issue_id)

    def create_issue(self, project: str, fields: dict) -> dict:
        return self._client().create_issue(project, fields)

    def update_issue(self, issue_id: int, fields: dict) -> None:
        self._client().update_issue(issue_id, fields)

    def get_user(self, user_id: int) -> dict:
        return self._client().get_user(user_id)


def make_redmine_mirror_router(
    *, office_store, require_actor, require_project, session_manager, cipher=None
) -> APIRouter:
    def _factory(base_url: str):
        del base_url
        url, _project, key = redmine_mirror.resolve_access(office_store, cipher, "", "")
        if not url or not key:
            raise redmine_mirror.MirrorError("no_key", "Ключ Redmine не задан")
        from src.office.redmine_mirror._http import HttpRedmine

        return HttpRedmine(url, key)

    async def _schedule() -> None:
        while True:
            try:
                await asyncio.to_thread(
                    redmine_mirror.run_due,
                    office_store,
                    users=session_manager,
                    client_factory=_factory,
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

    def _access(redmine_project: str) -> tuple[str, str, str]:
        return redmine_mirror.resolve_access(office_store, cipher, "", redmine_project)

    @router.post("/projects/{project_id}/redmine/load")
    async def load_project(body: _SyncIn, ctx: dict = Depends(require_project)) -> dict:
        url, project, key = _access(body.redmine_project)
        try:
            return await asyncio.to_thread(
                redmine_mirror.load_project,
                office_store,
                ctx["project"]["id"],
                actor_id=ctx["actor"]["user_id"],
                is_admin=ctx["actor"]["is_admin"],
                client=_LazyClient(url, key),
                users=session_manager,
                redmine_project=project,
                base_url=url,
            )
        except redmine_mirror.MirrorError as exc:
            raise _fail(exc) from exc

    @router.post("/projects/{project_id}/redmine/issues/{issue_id}/load")
    async def load_issue(
        issue_id: int, body: _UpdateIn, ctx: dict = Depends(require_project)
    ) -> dict:
        url, _project, key = _access("")
        try:
            return await asyncio.to_thread(
                redmine_mirror.load_issue,
                office_store,
                ctx["project"]["id"],
                issue_id,
                actor_id=ctx["actor"]["user_id"],
                is_admin=ctx["actor"]["is_admin"],
                client=_LazyClient(url, key),
                users=session_manager,
            )
        except redmine_mirror.MirrorError as exc:
            raise _fail(exc) from exc

    @router.post("/projects/{project_id}/redmine/issues")
    async def create_issue(body: _CreateIn, ctx: dict = Depends(require_project)) -> dict:
        url, project, key = _access(body.redmine_project)
        try:
            return await asyncio.to_thread(
                redmine_mirror.create_issue,
                office_store,
                ctx["project"]["id"],
                actor_id=ctx["actor"]["user_id"],
                is_admin=ctx["actor"]["is_admin"],
                client=_LazyClient(url, key),
                users=session_manager,
                request_key=body.request_key,
                redmine_project=project,
                subject=body.subject,
                description=body.description,
                status_id=body.status_id,
                assigned_to_id=body.assigned_to_id,
                start_date=body.start_date,
                due_date=body.due_date,
                notes=body.notes,
                base_url=url,
            )
        except redmine_mirror.MirrorError as exc:
            raise _fail(exc) from exc

    @router.put("/projects/{project_id}/redmine/issues/{issue_id}")
    async def update_issue(
        issue_id: int, body: _UpdateIn, ctx: dict = Depends(require_project)
    ) -> dict:
        url, _project, key = _access("")
        try:
            return await asyncio.to_thread(
                redmine_mirror.update_issue,
                office_store,
                ctx["project"]["id"],
                issue_id,
                actor_id=ctx["actor"]["user_id"],
                is_admin=ctx["actor"]["is_admin"],
                client=_LazyClient(url, key),
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
