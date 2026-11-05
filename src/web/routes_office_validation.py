"""Ручная валидация находок прогона под ``/api/office``.

Одна зависимость на весь роутер закрывает раздел от заказчика, поэтому новый
маршрут нельзя забыть закрыть. Адреса вложены в проект: плоский путь обошёл бы
``require_project``. Текст находок в журнал приложения не пишется.
"""
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from src.office import delivery, tenancy

log = structlog.get_logger()

_STATUS = {
    "not_found": 404,
    "customer": 403,
    "forbidden": 403,
    "export_banned": 403,
    "bad_input": 422,
    "bad_package": 422,
    "scan_failed": 422,
    "too_large": 413,
    "run_conflict": 409,
    "stale": 409,
    "bad_transition": 409,
    "files_stale": 503,
}


class _DecisionIn(BaseModel):
    action: str
    expected_seq: int
    request_key: str
    why: str = ""
    reason_code: str = ""
    doc_ref: str = ""


class _PolicyIn(BaseModel):
    export_ban: str


class _RedmineExportIn(BaseModel):
    api_key: str
    request_key: str


def _fail(exc: delivery.ValidationError) -> HTTPException:
    return HTTPException(status_code=_STATUS.get(exc.code, 422), detail=exc.message)


async def _call(func: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except delivery.ValidationError as exc:
        raise _fail(exc) from exc


async def _spool(request: Request, folder: Path) -> Path:
    """Тело запроса во временный файл с пределом: архив читается после проверки прав."""
    folder.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=folder, suffix=".zip", delete=False)
    size = 0
    with handle:
        async for chunk in request.stream():
            size += len(chunk)
            if size > delivery.MAX_ARCHIVE_BYTES:
                Path(handle.name).unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Архив слишком велик")
            handle.write(chunk)
    return Path(handle.name)


def make_validation_router(
    *,
    office_store: Any,
    require_project: Any,
    session_manager: Any,
) -> APIRouter:
    async def require_team(ctx: dict = Depends(require_project)) -> dict:
        actor = ctx["actor"]
        await _call(
            delivery.require_team, office_store, ctx["project"]["id"],
            actor_id=actor["user_id"], is_admin=actor["is_admin"],
        )
        return ctx

    async def require_manage(ctx: dict = Depends(require_team)) -> dict:
        actor = ctx["actor"]
        await _call(
            delivery.require_manage, office_store, ctx["project"]["id"],
            actor_id=actor["user_id"], is_admin=actor["is_admin"],
        )
        return ctx

    router = APIRouter(
        prefix="/projects/{project_id}/validation",
        tags=["office-validation"],
        dependencies=[Depends(require_team)],
    )

    def _named(rows: list[dict]) -> list[dict]:
        out = []
        for row in rows:
            user = session_manager.get_user_by_id(row["actor_id"]) if session_manager else None
            name = (user or {}).get("username") or "Участник"
            out.append({**{k: v for k, v in row.items() if k != "actor_id"}, "actor": name})
        return out

    @router.get("/runs")
    async def runs(ctx: dict = Depends(require_team)) -> dict:
        project_id, actor = ctx["project"]["id"], ctx["actor"]
        rows = await _call(delivery.list_runs, office_store, project_id)
        access = {"actor_id": actor["user_id"], "is_admin": actor["is_admin"]}
        return {
            "runs": rows,
            "can_decide": tenancy.can_decide(office_store, project_id, **access),
            "can_manage": tenancy.can_manage_validation(office_store, project_id, **access),
            "export_ban": await _call(delivery.get_policy, office_store, project_id),
        }

    @router.post("/runs/import", status_code=201)
    async def import_run(request: Request, ctx: dict = Depends(require_manage)) -> dict:
        project_id, actor = ctx["project"]["id"], ctx["actor"]
        path = await _spool(request, delivery.data_root(office_store) / ".incoming")
        try:
            return await _call(
                delivery.import_package, office_store, project_id, path,
                actor_id=actor["user_id"],
            )
        finally:
            path.unlink(missing_ok=True)

    @router.get("/runs/{run_id}")
    async def run_detail(run_id: int, ctx: dict = Depends(require_team)) -> dict:
        return await _call(delivery.get_run, office_store, ctx["project"]["id"], run_id)

    @router.get("/runs/{run_id}/findings")
    async def findings(run_id: int, ctx: dict = Depends(require_team)) -> list[dict]:
        await _call(delivery.get_run, office_store, ctx["project"]["id"], run_id)
        return await _call(delivery.list_findings, office_store, ctx["project"]["id"], run_id)

    @router.get("/runs/{run_id}/findings/{finding_id}")
    async def finding(run_id: int, finding_id: int, ctx: dict = Depends(require_team)) -> dict:
        data = await _call(
            delivery.get_finding, office_store, ctx["project"]["id"], run_id, finding_id,
        )
        data["history"] = await asyncio.to_thread(_named, data["history"])
        return data

    @router.post("/runs/{run_id}/findings/{finding_id}/decisions")
    async def decide(
        run_id: int, finding_id: int, body: _DecisionIn, ctx: dict = Depends(require_team),
    ) -> dict:
        project_id, actor = ctx["project"]["id"], ctx["actor"]
        role = await _call(
            delivery.require_decide, office_store, project_id,
            actor_id=actor["user_id"], is_admin=actor["is_admin"],
        )
        return await _call(
            delivery.decide, office_store, project_id, run_id, finding_id,
            action=body.action, actor_id=actor["user_id"], actor_role=role,
            expected_seq=body.expected_seq, request_key=body.request_key, why=body.why,
            reason_code=body.reason_code, doc_ref=body.doc_ref,
        )

    @router.post("/runs/{run_id}/findings/{finding_id}/redmine")
    async def export_redmine(
        run_id: int,
        finding_id: int,
        body: _RedmineExportIn,
        ctx: dict = Depends(require_team),
    ) -> dict:
        project_id = ctx["project"]["id"]
        result = await _call(
            delivery.export_finding_to_redmine,
            office_store,
            project_id,
            run_id,
            finding_id,
            api_key=body.api_key,
            request_key=body.request_key,
        )
        log.info(
            "validation_redmine_exported",
            project_id=project_id,
            run_id=run_id,
            finding_id=finding_id,
            issue_id=result["issue_id"],
            created=result["created"],
        )
        return result

    @router.post("/runs/{run_id}/redmine-stand-remediation")
    async def export_stand_remediation(
        run_id: int,
        body: _RedmineExportIn,
        ctx: dict = Depends(require_team),
    ) -> dict:
        project_id = ctx["project"]["id"]
        result = await _call(
            delivery.export_run_stand_remediation,
            office_store,
            project_id,
            run_id,
            api_key=body.api_key,
            request_key=body.request_key,
        )
        log.info(
            "validation_stand_remediation_redmine",
            project_id=project_id,
            run_id=run_id,
            issue_id=result["issue_id"],
            created=result["created"],
            findings=result["findings"],
        )
        return result

    @router.get("/runs/{run_id}/assets/{asset_id}")
    async def asset(run_id: int, asset_id: int, ctx: dict = Depends(require_team)) -> FileResponse:
        path, name, mime = await _call(
            delivery.asset_path, office_store, ctx["project"]["id"], run_id, asset_id,
        )
        return FileResponse(
            path, filename=name, media_type=mime, content_disposition_type="inline",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @router.put("/policy")
    async def policy(body: _PolicyIn, ctx: dict = Depends(require_manage)) -> dict:
        project_id, actor = ctx["project"]["id"], ctx["actor"]
        value = await _call(
            delivery.set_policy, office_store, project_id, body.export_ban,
            actor_id=actor["user_id"],
            at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        log.info("validation_policy_changed", project_id=project_id, value=value)
        return {"export_ban": value}

    @router.post("/runs/{run_id}/export")
    async def export(run_id: int, ctx: dict = Depends(require_manage)) -> Response:
        project_id, actor = ctx["project"]["id"], ctx["actor"]
        data, name = await _call(
            delivery.export_run, office_store, project_id, run_id, actor_id=actor["user_id"],
        )
        log.info("validation_exported", project_id=project_id, run_id=run_id, size=len(data))
        return Response(
            content=data, media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
