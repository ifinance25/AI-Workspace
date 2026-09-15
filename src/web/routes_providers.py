"""REST /api/providers: ключи и модели по провайдерам (Claude, OpenAI, Cursor, Kimi).

GET возвращает только метаданные (status / last4), никогда сам ключ.
Когда ``api_key_store`` is None, все глаголы отвечают 501.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.apikeys.providers import PROVIDER_IDS, catalog_payload, get_spec
from src.apikeys.validate import ProbeResult, probe_key, validate_key_format
from src.web.dependencies import get_current_user_factory
from src.web.routes_apikey import _resolve_privileged

logger = structlog.get_logger()


class ProviderPutIn(BaseModel):
    api_key: str | None = None
    oauth_token: str | None = None
    base_url: str | None = None
    model: str | None = None


class ActiveIn(BaseModel):
    provider: str
    model: str | None = None


def _safe_base_url(raw: str) -> str:
    """Только http(s) URL без пробелов и обрезка хвоста."""
    value = (raw or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="base_url must be an http(s) URL",
        )
    if len(value) > 500:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="base_url too long",
        )
    return value.rstrip("/")


def make_providers_router(
    *,
    jwt_secret: str,
    session_manager,
    api_key_store,
    allowed_user_ids: list[int] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/providers", tags=["providers"])
    whitelist = set(allowed_user_ids or [])
    get_current_user = get_current_user_factory(jwt_secret, session_manager, whitelist)

    def _require_store() -> None:
        if api_key_store is None:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="api key store not configured",
            )

    async def _save_secret(
        uid: int,
        provider: str,
        secret: str,
        *,
        auth_kind: str,
        extra: dict | None,
    ) -> dict:
        if not validate_key_format(secret, provider=provider, auth_kind=auth_kind):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid key format",
            )
        if auth_kind == "oauth":
            await asyncio.to_thread(
                api_key_store.set_key,
                uid,
                secret,
                status="active",
                provider=provider,
                auth_kind="oauth",
                extra=extra,
            )
            logger.info("web_provider_saved", user_id=uid, provider=provider, status="active")
            return {"status": "active", "message": "Подписка сохранена"}

        probe = await probe_key(secret, provider=provider)
        if probe is ProbeResult.INVALID:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="API key failed validation (401 Unauthorized)",
            )
        row_status = "active" if probe is ProbeResult.VALID else "unverified"
        await asyncio.to_thread(
            api_key_store.set_key,
            uid,
            secret,
            status=row_status,
            provider=provider,
            auth_kind="api_key",
            extra=extra,
        )
        logger.info(
            "web_provider_saved", user_id=uid, provider=provider, status=row_status
        )
        if row_status == "unverified":
            return {
                "status": "unverified",
                "message": "API key saved",
                "warning": "Could not verify the key against the provider API "
                "(network error). Saved as unverified.",
            }
        return {"status": "active", "message": "API key saved"}

    @router.get("")
    async def list_providers(user: dict = Depends(get_current_user)) -> dict:
        _require_store()
        uid = int(user["user_id"])
        privileged = await _resolve_privileged(user, whitelist, session_manager)
        prefs = await asyncio.to_thread(api_key_store.get_prefs, uid)
        metas = await asyncio.to_thread(api_key_store.list_meta, uid)
        providers = []
        for spec in catalog_payload():
            pid = spec["id"]
            meta = metas.get(pid)
            models_map = prefs.get("models") or {}
            current_model = models_map.get(pid) or spec["default_model"]
            extra = (meta or {}).get("extra") or {}
            providers.append(
                {
                    **spec,
                    "connected": meta is not None,
                    "status": (meta or {}).get("status"),
                    "last4": (meta or {}).get("last4"),
                    "auth_kind": (meta or {}).get("auth_kind"),
                    "base_url": extra.get("base_url") or spec.get("base_url"),
                    "current_model": current_model,
                    "active": prefs.get("active_provider") == pid,
                }
            )
        return {
            "enabled": True,
            "privileged": privileged,
            "active_provider": prefs.get("active_provider") or "claude",
            "providers": providers,
        }

    @router.put("/{provider_id}")
    async def put_provider(
        provider_id: str,
        payload: ProviderPutIn,
        user: dict = Depends(get_current_user),
    ) -> dict:
        _require_store()
        spec = get_spec(provider_id)
        if spec is None:
            raise HTTPException(status_code=404, detail="unknown provider")
        uid = int(user["user_id"])
        extra = None
        if payload.base_url is not None:
            extra = {"base_url": _safe_base_url(payload.base_url)}

        result: dict = {"status": "ok"}
        secret = (payload.oauth_token or payload.api_key or "").strip()
        auth_kind = "oauth" if (payload.oauth_token or "").strip() else "api_key"
        if secret:
            result = await _save_secret(
                uid, provider_id, secret, auth_kind=auth_kind, extra=extra
            )
        elif extra is not None:
            await asyncio.to_thread(
                api_key_store.set_provider_extra, uid, provider_id, extra
            )
            result = {"status": "ok", "message": "Настройки сохранены"}

        if payload.model:
            allowed = {m.id for m in spec.models}
            if payload.model not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="unknown model for this provider",
                )
            await asyncio.to_thread(
                api_key_store.set_prefs,
                uid,
                active_provider=provider_id,
                model=payload.model,
                provider_for_model=provider_id,
            )
            result["current_model"] = payload.model
            result["active_provider"] = provider_id
        elif not secret and extra is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="nothing to save",
            )
        return result

    @router.delete("/{provider_id}")
    async def delete_provider(
        provider_id: str,
        user: dict = Depends(get_current_user),
    ) -> dict:
        _require_store()
        if provider_id not in PROVIDER_IDS:
            raise HTTPException(status_code=404, detail="unknown provider")
        uid = int(user["user_id"])
        await asyncio.to_thread(api_key_store.delete_key, uid, provider_id)
        logger.info("web_provider_deleted", user_id=uid, provider=provider_id)
        return {"message": "API key deleted"}

    @router.patch("/active")
    async def set_active(
        payload: ActiveIn,
        user: dict = Depends(get_current_user),
    ) -> dict:
        _require_store()
        spec = get_spec(payload.provider)
        if spec is None:
            raise HTTPException(status_code=404, detail="unknown provider")
        model = payload.model
        if model:
            allowed = {m.id for m in spec.models}
            if model not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="unknown model for this provider",
                )
        uid = int(user["user_id"])
        prefs = await asyncio.to_thread(
            api_key_store.set_prefs,
            uid,
            active_provider=payload.provider,
            model=model,
            provider_for_model=payload.provider,
        )
        return {
            "active_provider": prefs["active_provider"],
            "models": prefs["models"],
        }

    return router
