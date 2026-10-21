"""Бриф проекта офиса: роутер границы ``project`` (документ ``brief``). Заполняет таск 03.

Пути задавать относительно ``/api/office`` (префикс добавляет ``routes_office``),
например ``/projects/{project_id}/brief``.
"""
from __future__ import annotations

from fastapi import APIRouter


def make_office_brief_router(*, office_store, require_actor, require_project) -> APIRouter:
    router = APIRouter(tags=["office-brief"])
    return router
