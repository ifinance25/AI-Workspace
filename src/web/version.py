"""Версия запущенного сервера для экрана настроек: коммит, дата коммита, время запуска.

Читается из git один раз при старте процесса. Нет git (установка из архива): берётся файл
VERSION в корне, иначе «неизвестно». Секретов здесь нет, но маршрут всё равно за входом.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends

from src.web.dependencies import get_current_user_factory

_ROOT = Path(__file__).resolve().parents[2]
_STARTED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _from_git() -> tuple[str, str] | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(_ROOT), "log", "-1", "--format=%h|%cI"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    commit, _, committed_at = out.partition("|")
    return (commit, committed_at) if commit else None


def _from_file() -> tuple[str, str] | None:
    try:
        text = (_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return (text.split()[0], "") if text else None


def read_version() -> dict[str, str]:
    found = _from_git() or _from_file()
    commit, committed_at = found if found else ("неизвестно", "")
    return {"commit": commit, "committed_at": committed_at, "started_at": _STARTED_AT}


_VERSION = read_version()


def make_version_router(*, jwt_secret: str, session_manager, allowed_user_ids=None) -> APIRouter:
    router = APIRouter(tags=["version"])
    get_current_user = get_current_user_factory(
        jwt_secret, session_manager, set(allowed_user_ids or [])
    )

    @router.get("/api/version")
    async def get_version(_user: dict = Depends(get_current_user)) -> dict[str, str]:
        return _VERSION

    return router
