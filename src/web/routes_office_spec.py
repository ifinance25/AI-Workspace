"""Задание проекта офиса: роутер границы ``cycle`` (документ ``spec``). Заполняет таск 04.

Пути задавать относительно ``/api/office`` (префикс добавляет ``routes_office``),
например ``/projects/{project_id}/spec``.
"""
from __future__ import annotations

from fastapi import APIRouter


def make_office_spec_router(*, office_store, require_actor, require_project) -> APIRouter:
    router = APIRouter(tags=["office-spec"])
    return router
