"""Каталог LLM-провайдеров и запуск сессии с выбранным балансом.

Форма «Модель» группирует ключи и модели по провайдерам. Claude Code остаётся
основным агентом (инструменты, файлы, терминал). Kimi идёт через Anthropic-
совместимый API Moonshot. OpenAI и Cursor сохраняют ключ; если задан базовый
URL в формате Anthropic (прокси вроде LiteLLM), агент стартует на этом ключе.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.apikeys.policy import NeedsApiKeyError, resolve_session_auth
from src.claude.models import DEFAULT_MODEL, KNOWN_MODELS


@dataclass(frozen=True)
class ProviderModel:
    id: str
    label: str
    hint: str


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    description: str
    key_placeholder: str
    key_hint: str
    how_to_url: str
    models: tuple[ProviderModel, ...]
    default_model: str
    # Anthropic-совместимый endpoint → Claude Code понимает его напрямую.
    base_url: str | None = None
    base_url_editable: bool = False
    oauth_url: str | None = None
    oauth_label: str | None = None
    extra_env_key: str | None = None


def _claude_models() -> tuple[ProviderModel, ...]:
    """Haiku / Sonnet / Opus: те же pinned id, короткие подписи в форме."""
    short = {
        "haiku": ("Haiku", "Быстрый и дешёвый: лёгкие задачи"),
        "sonnet": ("Sonnet", "Сбалансированный: основная рабочая модель"),
        "opus": ("Opus", "Самый сильный: сложные задачи, дороже"),
    }
    by_family: dict[str, ProviderModel] = {}
    for row in KNOWN_MODELS:
        key = next((k for k in short if k in row["id"]), None)
        if key is None:
            continue
        label, hint = short[key]
        by_family[key] = ProviderModel(id=row["id"], label=label, hint=hint)
    return tuple(
        by_family[name] for name in ("haiku", "sonnet", "opus") if name in by_family
    )


PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="claude",
        label="Claude Code",
        description="Подписка Claude (вход в браузере) или ключ Anthropic.",
        key_placeholder="sk-ant-…",
        key_hint="Ключ с console.anthropic.com, если платите API, а не подпиской.",
        how_to_url="https://console.anthropic.com/settings/keys",
        models=_claude_models(),
        default_model=DEFAULT_MODEL,
        oauth_url="https://claude.ai/login",
        oauth_label="Подключить подписку",
    ),
    ProviderSpec(
        id="openai",
        label="OpenAI",
        description="Ключ с platform.openai.com. Для агента нужен Anthropic-прокси.",
        key_placeholder="sk-…",
        key_hint="Ключ OpenAI. Базовый URL: только если есть прокси в формате Anthropic.",
        how_to_url="https://platform.openai.com/api-keys",
        models=(
            ProviderModel("gpt-5", "GPT-5", "Новая основная модель OpenAI"),
            ProviderModel("gpt-4.1", "GPT-4.1", "Сильный и стабильный"),
            ProviderModel("o3", "o3", "Рассуждения, медленнее и дороже"),
        ),
        default_model="gpt-4.1",
        base_url_editable=True,
        extra_env_key="OPENAI_API_KEY",
    ),
    ProviderSpec(
        id="cursor",
        label="Cursor API",
        description="Ключ Cursor: cursor.com → Dashboard → API Keys.",
        key_placeholder="key_…",
        key_hint="Ключ Cursor. Базовый URL: прокси в формате Anthropic, если есть.",
        how_to_url="https://cursor.com/dashboard?tab=integrations",
        models=(
            ProviderModel("composer-2", "Composer", "Модель Cursor для кода"),
            ProviderModel("auto", "Auto", "Cursor сам выбирает модель"),
            ProviderModel("grok-4", "Grok 4", "Через баланс Cursor"),
            ProviderModel("gpt-5", "GPT-5", "Через баланс Cursor"),
        ),
        default_model="composer-2",
        base_url_editable=True,
        extra_env_key="CURSOR_API_KEY",
    ),
    ProviderSpec(
        id="kimi",
        label="Kimi Code",
        description="Moonshot Kimi: агент идёт через совместимый с Claude API.",
        key_placeholder="sk-…",
        key_hint="Ключ с platform.moonshot.ai или platform.moonshot.cn.",
        how_to_url="https://platform.moonshot.ai/console/api-keys",
        models=(
            ProviderModel(
                "kimi-k2.5", "Kimi K2.5", "Основная модель Kimi для кода"
            ),
            ProviderModel(
                "kimi-k2-0905-preview",
                "Kimi K2",
                "Предыдущая K2, если на счёте только она",
            ),
        ),
        default_model="kimi-k2.5",
        base_url="https://api.moonshot.ai/anthropic",
    ),
)

PROVIDER_IDS = {p.id for p in PROVIDER_SPECS}


def get_spec(provider_id: str) -> ProviderSpec | None:
    for spec in PROVIDER_SPECS:
        if spec.id == provider_id:
            return spec
    return None


def all_model_ids() -> set[str]:
    ids: set[str] = set()
    for spec in PROVIDER_SPECS:
        for m in spec.models:
            ids.add(m.id)
    return ids


def model_provider(model_id: str) -> str | None:
    """Первый провайдер, у которого есть эта модель (claude важнее дублей)."""
    for spec in PROVIDER_SPECS:
        if any(m.id == model_id for m in spec.models):
            return spec.id
    return None


def catalog_payload() -> list[dict[str, Any]]:
    """Публичное описание провайдеров (без секретов) для GET /api/providers."""
    out: list[dict[str, Any]] = []
    for spec in PROVIDER_SPECS:
        out.append(
            {
                "id": spec.id,
                "label": spec.label,
                "description": spec.description,
                "key_placeholder": spec.key_placeholder,
                "key_hint": spec.key_hint,
                "how_to_url": spec.how_to_url,
                "oauth_url": spec.oauth_url,
                "oauth_label": spec.oauth_label,
                "base_url": spec.base_url,
                "base_url_editable": spec.base_url_editable,
                "default_model": spec.default_model,
                "models": [
                    {"id": m.id, "label": m.label, "hint": m.hint} for m in spec.models
                ],
            }
        )
    return out


@dataclass
class LlmLaunch:
    """Что инжектить в Claude Code для выбранного провайдера."""

    provider: str
    model: str | None
    api_key: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)


def launch_for_user(
    store: Any,
    user_id: int,
    *,
    is_privileged: bool,
    require_user_key: bool,
) -> LlmLaunch:
    """Ключ + env для спавна. Старые сторы без get_prefs ведут себя как раньше."""
    if store is None or not callable(getattr(store, "get_prefs", None)):
        user_key = store.get_key(user_id) if store is not None else None
        decision = resolve_session_auth(
            is_privileged=is_privileged,
            user_key=user_key,
            require_user_key=require_user_key,
        )
        return LlmLaunch(
            provider="claude",
            model=None,
            api_key=decision.api_key,
        )

    prefs = store.get_prefs(user_id)
    provider = prefs.get("active_provider") or "claude"
    spec = get_spec(provider) or get_spec("claude")
    assert spec is not None
    models_map = prefs.get("models") or {}
    model = models_map.get(spec.id) or spec.default_model

    key = store.get_key(user_id, spec.id)
    meta = store.get_provider_meta(user_id, spec.id)
    auth_kind = (meta or {}).get("auth_kind") or "api_key"
    extra = (meta or {}).get("extra") or {}

    if spec.id != "claude" and not key:
        raise NeedsApiKeyError(f"Подключите ключ {spec.label} в Настройки → Модель")

    extra_env: dict[str, str] = {}
    api_key: str | None = None

    if spec.id == "claude":
        decision = resolve_session_auth(
            is_privileged=is_privileged,
            user_key=key,
            require_user_key=require_user_key,
        )
        if decision.api_key and auth_kind == "oauth":
            extra_env["CLAUDE_CODE_OAUTH_TOKEN"] = decision.api_key
            return LlmLaunch(
                provider="claude",
                model=model,
                api_key=None,
                extra_env=extra_env,
            )
        return LlmLaunch(
            provider="claude",
            model=model,
            api_key=decision.api_key,
        )

    base = (extra.get("base_url") or spec.base_url or "").strip()
    if base:
        extra_env["ANTHROPIC_BASE_URL"] = base
    if spec.extra_env_key and key:
        extra_env[spec.extra_env_key] = key
    api_key = key
    if not base and spec.id in {"openai", "cursor"}:
        raise NeedsApiKeyError(
            f"{spec.label}: для агента нужен базовый URL в формате Anthropic "
            "(прокси) или выберите Claude / Kimi, где агент уже работает."
        )
    return LlmLaunch(
        provider=spec.id,
        model=model,
        api_key=api_key,
        extra_env=extra_env,
    )
