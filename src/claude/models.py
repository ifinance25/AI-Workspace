"""Single source of truth for Claude model ids/labels used by both the web
``/api/model`` route and the Telegram bot's ``/model`` handler.

Kept provider-neutral (no fastapi/aiogram imports) so any layer can import it
without pulling in a framework. Mirrors the pinned-id rationale that used to
live in ``src/web/routes_model.py``: we write explicit versioned ids into
``~/.claude/settings.json`` so Claude doesn't silently swap "latest".
"""
from __future__ import annotations

import re

# Pinned explicit model ids (не алиасы opus/sonnet/haiku) — чтобы выбор
# детерминированно писал конкретную версию в settings.json.
KNOWN_MODELS: list[dict[str, str]] = [
    {
        "id": "claude-fable-5-1",
        "label": "Claude Fable 5.1",
        "hint": "Самая новая и мощная — для самых сложных задач.",
    },
    {
        "id": "claude-sonnet-5-5",
        "label": "Claude Sonnet 5.5",
        "hint": "Сбалансированный — рабочая лошадка для большинства задач.",
    },
    {
        "id": "claude-opus-5-5",
        "label": "Claude Opus 5.5",
        "hint": "Самый сильный — для сложных задач, дороже по токенам.",
    },
    {
        "id": "claude-haiku-5-5",
        "label": "Claude Haiku 5.5",
        "hint": "Быстрый и дешёвый — для лёгких задач и стриминга.",
    },
]

# Default model when settings.json has none yet.
DEFAULT_MODEL = "claude-sonnet-5-5"

# Старые алиасы → pinned id (для отображения "текущей" и текстового /model).
ALIAS_TO_ID: dict[str, str] = {
    "fable": "claude-fable-5-1",
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
}


def valid_model_ids() -> set[str]:
    """Allowlist of pinned ids that may be written to settings.json."""
    return {m["id"] for m in KNOWN_MODELS}


def normalize_model_id(raw: str) -> str:
    """Map a stored alias to its pinned id (для подсветки текущей); иначе как есть."""
    return ALIAS_TO_ID.get(raw, raw)


def resolve_model_input(token: str) -> str | None:
    """Текстовый ``/model <token>``: known алиас/id → канонический pinned id.

    Возвращает ``None`` для пустого/с пробелами/слишком длинного/неизвестного —
    строгий allowlist, т.к. значение уходит в общий settings.json.
    """
    t = (token or "").strip()
    if not t or any(ch.isspace() for ch in t) or len(t) > 128:
        return None
    if t in ALIAS_TO_ID:
        return ALIAS_TO_ID[t]
    if t in valid_model_ids():
        return t
    return None


_SAFE_ID_RE = re.compile(r"^claude-[a-z0-9][a-z0-9.\-]*$")
_SNAPSHOT_RE = re.compile(r"^\d{8}$")
_REVISION_RE = re.compile(r"^v\d+$")


def is_safe_model_id(model_id: str) -> bool:
    """Строгий формат id: значение пишется дословно в общий settings.json."""
    return bool(model_id) and len(model_id) <= 128 and bool(_SAFE_ID_RE.match(model_id))


def humanize_model_id(model_id: str) -> str:
    """Читаемое имя без сети: ``claude-opus-5-5`` → ``Claude Opus 5.5``.

    Хвосты-снапшоты (``20251101``, ``v1``) отбрасываются, режим (``fast``)
    остаётся. Чужой формат и пустую строку возвращаем как есть.
    """
    if not model_id or not model_id.startswith("claude-"):
        return model_id
    tokens = [
        t
        for t in model_id.split("-")[1:]
        if t and not _SNAPSHOT_RE.match(t) and not _REVISION_RE.match(t)
    ]
    numbers = [t for t in tokens if t.isdigit()]
    words = [t.capitalize() for t in tokens if not t.isdigit()]
    if not words and not numbers:
        return model_id
    parts = ["Claude", *words[:1]]
    if numbers:
        parts.append(".".join(numbers))
    parts.extend(words[1:])
    return " ".join(parts)


def model_label(model_id: str) -> str:
    """Human label for a pinned id; a readable name when unknown."""
    for m in KNOWN_MODELS:
        if m["id"] == model_id:
            return m["label"]
    return humanize_model_id(model_id)


def model_hint(model_id: str) -> str:
    """One-line hint for a pinned id; empty string when unknown."""
    for m in KNOWN_MODELS:
        if m["id"] == model_id:
            return m["hint"]
    return ""
