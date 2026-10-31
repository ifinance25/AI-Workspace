"""Переходы находки. Две оси: решение проверяющего и этап жизни из контракта QA.

``TRANSITIONS`` повторяет контракт Э9 з.6. Единственное дополнение
``reopened → confirmed``: человек вернул находку в разбор и подтвердил её.
"""
from __future__ import annotations

from src.office.delivery._validation_schema import ValidationError

TRANSITIONS: dict[str, frozenset[str]] = {
    "new": frozenset({"confirmed", "rejected", "duplicate"}),
    "confirmed": frozenset({"submitted", "in_progress", "rejected", "duplicate"}),
    "submitted": frozenset({"in_progress", "fixed", "rejected", "duplicate"}),
    "in_progress": frozenset({"fixed", "rejected"}),
    "fixed": frozenset({"retested", "reopened"}),
    "retested": frozenset({"closed", "reopened"}),
    "reopened": frozenset({"in_progress", "fixed", "rejected", "confirmed"}),
    "closed": frozenset({"reopened"}),
    "rejected": frozenset({"reopened"}),
    "duplicate": frozenset(),
}

ACTIONS = ("confirm", "reject", "clarify", "edits_applied", "reopen")
REASON_CODES = frozenset({
    "wrong_fact", "no_basis", "contradicts_customer", "contradicts_decision",
    "out_of_scope", "outdated_input", "unclear", "style", "other",
})
DEFAULT_WHY = {
    "confirm": "Подтверждено проверяющим",
    "edits_applied": "Правки внесены в документы",
    "reopen": "Возвращено в разбор",
}


def plan_steps(action: str, review: str, lifecycle: str) -> list[tuple[str, str]]:
    """Шаги ``(решение, этап)`` действия или отказ 409 для недопустимого перехода."""
    if action == "confirm" and review in ("new", "needs_info"):
        return [("confirmed", "confirmed")]
    if action == "reject" and review in ("new", "needs_info", "confirmed"):
        if lifecycle not in ("submitted", "fixed"):
            return [("rejected", "rejected")]
    if action == "clarify" and review in ("new", "needs_info", "confirmed"):
        if lifecycle != "fixed":
            return [("needs_info", lifecycle)]
    if action == "edits_applied" and review == "confirmed" and lifecycle == "confirmed":
        return [("confirmed", "submitted"), ("confirmed", "fixed")]
    if action == "reopen" and lifecycle in ("rejected", "fixed"):
        return [("new", "reopened")]
    raise ValidationError(
        "bad_transition", f"Действие недоступно: статус {review}, этап {lifecycle}"
    )


def assert_allowed(lifecycle_from: str, lifecycle_to: str) -> None:
    if lifecycle_from != lifecycle_to and lifecycle_to not in TRANSITIONS[lifecycle_from]:
        raise ValidationError(
            "bad_transition", f"Переход {lifecycle_from} в {lifecycle_to} запрещён"
        )
