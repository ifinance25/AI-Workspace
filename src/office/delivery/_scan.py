"""Сканер ключей и личных данных по образцам. Псевдонимы ``28`` он не заменяет.

Отвечает видами находок, сам текст наружу не отдаёт.
"""
from __future__ import annotations

import re

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(
        r"(?<![\d.-])(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)"
    )),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("api_key", re.compile(
        r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}"
        r"|xox[baprs]-[A-Za-z0-9-]{10,})\b"
    )),
    ("bearer", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("assignment", re.compile(
        r"(?i)\b(?:password|passwd|пароль|token|токен|secret|api[_-]?key)\s*[:=]\s*\S{6,}"
    )),
    ("fio", re.compile(
        r"\b[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:ович|евич|овна|евна|ична|инична)\b"
    )),
    ("fio_short", re.compile(r"\b[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.")),
)


def scan(text: str) -> list[str]:
    """Отсортированные виды находок в тексте."""
    return sorted({kind for kind, rule in _RULES if rule.search(text or "")})
