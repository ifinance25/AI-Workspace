"""Паспорт проекта офиса: роутер границы ``project``. Заполняет таск 02.

Пути задавать относительно ``/api/office`` (префикс добавляет ``routes_office``),
например ``/projects`` и ``/projects/{project_id}/passport``.
"""
from __future__ import annotations

from fastapi import APIRouter


def make_office_project_router(*, office_store, require_actor, require_project) -> APIRouter:
    router = APIRouter(tags=["office-project"])
    return router
