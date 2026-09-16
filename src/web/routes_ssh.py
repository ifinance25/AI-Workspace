"""REST /api/ssh and WebSocket /api/ws/ssh for the in-panel terminal."""
from __future__ import annotations

import asyncio
import re

import structlog
from fastapi import APIRouter, Depends, HTTPException, WebSocket, status
from pydantic import BaseModel, Field

from src.ssh.keys import InvalidSshKeyError, fingerprint_private_key
from src.ssh.session import bridge_ssh_websocket
from src.ssh.store import SshProfile, SshStore
from src.web.auth import decode_jwt
from src.web.dependencies import get_current_user_factory, is_account_active
from src.web.origin_check import is_allowed_origin

logger = structlog.get_logger()

_HOST_RE = re.compile(r"^[A-Za-z0-9._:\-\[\]]{1,253}$")
_USER_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MAX_SSH_WS_PER_USER = 2


class SshPutIn(BaseModel):
    host: str = Field(..., min_length=1, max_length=253)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=64)
    private_key: str | None = Field(default=None, max_length=32_768)
    passphrase: str | None = Field(default=None, max_length=256)


def _public_profile(store_enabled: bool, profile: SshProfile | None) -> dict:
    if profile is None:
        return {
            "enabled": store_enabled,
            "configured": False,
            "host": "",
            "port": 22,
            "username": "",
            "has_key": False,
            "fingerprint": None,
        }
    return {
        "enabled": store_enabled,
        "configured": True,
        "host": profile.host,
        "port": profile.port,
        "username": profile.username,
        "has_key": bool(profile.private_key),
        "fingerprint": profile.fingerprint or None,
    }


def _clean_host(raw: str) -> str:
    host = raw.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not host or _HOST_RE.match(host) is None:
        raise HTTPException(status_code=422, detail="Некорректный адрес сервера")
    return host


def _clean_username(raw: str) -> str:
    name = raw.strip()
    if _USER_RE.match(name) is None:
        raise HTTPException(status_code=422, detail="Некорректное имя пользователя")
    return name


def make_ssh_router(
    *,
    jwt_secret: str,
    session_manager,
    ssh_store: SshStore | None,
    allowed_user_ids: list[int] | None = None,
    allowed_origins: set[str] | None = None,
    allow_loopback_origin: bool = True,
) -> APIRouter:
    router = APIRouter(tags=["ssh"])
    get_current_user = get_current_user_factory(
        jwt_secret, session_manager, set(allowed_user_ids or [])
    )
    whitelist = set(allowed_user_ids or [])
    ws_allowed_origins = allowed_origins or set()
    ws_conn_counts: dict[int, int] = {}

    @router.get("/api/ssh")
    async def get_ssh(user: dict = Depends(get_current_user)) -> dict:
        if ssh_store is None:
            return _public_profile(False, None)
        profile = await asyncio.to_thread(ssh_store.get, int(user["user_id"]))
        return _public_profile(True, profile)

    @router.put("/api/ssh")
    async def put_ssh(
        payload: SshPutIn, user: dict = Depends(get_current_user)
    ) -> dict:
        if ssh_store is None:
            raise HTTPException(
                status_code=503,
                detail="SSH выключен: на сервере не задан ключ шифрования",
            )
        uid = int(user["user_id"])
        existing = await asyncio.to_thread(ssh_store.get, uid)
        host = _clean_host(payload.host)
        username = _clean_username(payload.username)
        new_key = (payload.private_key or "").strip()
        passphrase = (payload.passphrase or "").strip() or None
        if new_key:
            key_text = new_key
            key_pass = passphrase
        elif existing and existing.private_key:
            key_text = existing.private_key
            key_pass = passphrase if payload.passphrase is not None else existing.passphrase
        else:
            raise HTTPException(
                status_code=422,
                detail="Вставьте закрытый SSH-ключ",
            )
        try:
            fingerprint = fingerprint_private_key(key_text, key_pass)
        except InvalidSshKeyError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        profile = SshProfile(
            host=host,
            port=payload.port,
            username=username,
            private_key=key_text,
            passphrase=key_pass,
            fingerprint=fingerprint,
        )
        await asyncio.to_thread(ssh_store.save, uid, profile)
        return _public_profile(True, profile)

    @router.delete("/api/ssh")
    async def delete_ssh(user: dict = Depends(get_current_user)) -> dict:
        if ssh_store is None:
            raise HTTPException(
                status_code=503,
                detail="SSH выключен: на сервере не задан ключ шифрования",
            )
        ok = await asyncio.to_thread(ssh_store.delete, int(user["user_id"]))
        if not ok:
            raise HTTPException(status_code=404, detail="Профиль SSH не найден")
        return {"ok": True}

    @router.websocket("/api/ws/ssh")
    async def ws_ssh(websocket: WebSocket) -> None:
        if not is_allowed_origin(
            websocket.headers.get("origin"),
            websocket.headers.get("host"),
            ws_allowed_origins,
            allow_loopback=allow_loopback_origin,
        ):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        cookie = websocket.cookies.get("vels_session")
        if not cookie:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        try:
            user = decode_jwt(cookie, secret=jwt_secret)
        except ValueError:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        user_id = int(user["user_id"])
        if not await is_account_active(session_manager, user, whitelist):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if ssh_store is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        profile = await asyncio.to_thread(ssh_store.get, user_id)
        if profile is None or not profile.private_key or not profile.host:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        if ws_conn_counts.get(user_id, 0) >= MAX_SSH_WS_PER_USER:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        await websocket.accept()
        ws_conn_counts[user_id] = ws_conn_counts.get(user_id, 0) + 1
        try:
            await bridge_ssh_websocket(websocket, profile)
        finally:
            remaining = ws_conn_counts.get(user_id, 1) - 1
            if remaining > 0:
                ws_conn_counts[user_id] = remaining
            else:
                ws_conn_counts.pop(user_id, None)

    return router
