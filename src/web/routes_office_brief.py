"""Бриф проекта офиса (документ ``brief``): приём текста и файла, версии.

Пути относительно ``/api/office`` (префикс добавляет ``routes_office``). В
хранилище роутер ходит только через ``knowledge``. Доступ решает
``require_project``: чужой и несуществующий проект отдают 404.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.office import knowledge
from src.web import routes_files

BRIEF = "brief"
_STATUS = {"empty": 400, "unreadable": 400, "unsupported": 415}


class BriefText(BaseModel):
    text: str = ""


def make_office_brief_router(*, office_store, require_actor, require_project) -> APIRouter:
    router = APIRouter(tags=["office-brief"])

    async def _ingest(operation, ctx: dict[str, Any], **kwargs: Any) -> JSONResponse:
        try:
            result = await asyncio.to_thread(
                operation,
                office_store,
                ctx["project"]["id"],
                kind=BRIEF,
                created_by=ctx["actor"]["user_id"],
                **kwargs,
            )
        except knowledge.IngestError as exc:
            raise HTTPException(status_code=_STATUS.get(exc.code, 400), detail=str(exc)) from exc
        return JSONResponse(result, status_code=201 if result["created"] else 200)

    @router.post("/projects/{project_id}/brief")
    async def save_text(
        body: BriefText,
        ctx: dict[str, Any] = Depends(require_project),
    ) -> JSONResponse:
        return await _ingest(
            knowledge.ingest, ctx, markdown=body.text, source=knowledge.TEXT_SOURCE
        )

    @router.post("/projects/{project_id}/brief/file")
    async def save_file(
        file: UploadFile = File(...),
        ctx: dict[str, Any] = Depends(require_project),
    ) -> JSONResponse:
        limit = routes_files.MAX_UPLOAD_BYTES
        data = await file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Файл больше {limit // (1024 * 1024)} МБ: уменьшите его.",
            )
        return await _ingest(knowledge.ingest_file, ctx, filename=file.filename or "", data=data)

    @router.get("/projects/{project_id}/brief/versions")
    async def list_versions(ctx: dict[str, Any] = Depends(require_project)) -> list[dict]:
        return await asyncio.to_thread(
            knowledge.versions,
            office_store,
            ctx["project"]["id"],
            BRIEF,
        )

    @router.get("/projects/{project_id}/brief/versions/{number}")
    async def get_version(
        number: int,
        ctx: dict[str, Any] = Depends(require_project),
    ) -> dict:
        found = await asyncio.to_thread(
            knowledge.version,
            office_store,
            ctx["project"]["id"],
            BRIEF,
            number,
        )
        if found is None:
            raise HTTPException(status_code=404, detail="Версия не найдена")
        return found

    return router
