"""Правила раздела ФТТ и часы цикла. Данные модуля, снаружи не читаются.

Слова разделов и формула часов взяты из сборки дашборда. Календарь на 2026 год
лежит здесь же: пятидневка, 8 часов, короткий день до 17:00, праздники без часов.
Учёт часов Redmine не используется.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

# \w как в сборке дашборда: только латиница и цифры, не буква русского слова.
_WORD = re.ASCII

FTT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Требования к визуальной адаптации личного кабинета", (
        r"визуальн\w*\s+адаптац", r"личн\w*\s+кабинет", r"макет\w*\s+личн\w*",
    )),
    ("База знаний", (
        r"баз\w*\s+знани", r"стать\w*", r"категор\w*", r"комментари\w*",
        r"реакци\w*", r"тег\w*", r"лайк\w*", r"печатн\w*\s+форм\w*",
    )),
    ("Индивидуальный план развития", (r"индивидуальн\w*\s+план\w*\s+развит", r"\bипр\b")),
    ("Управление электронным обучением", (
        r"электронн\w*\s+обучен", r"обучен\w*", r"курс\w*",
    )),
    ("Организационная структура", (
        r"организационн\w*\s+структур", r"оргструктур", r"подразделен\w*",
        r"должност\w*", r"контакт\w*", r"сотрудник\w*",
    )),
    ("Цифровой профиль", (r"цифров\w*\s+профил", r"личн\w*\s+профил", r"профил\w*")),
    ("Новостная лента", (r"новост\w*", r"лент\w*", r"публик\w*", r"пост\w*")),
    ("Спасибо", (r"спасиб\w*",)),
    ("Дни рождения", (r"дн\w*\s+рождени",)),
    ("Временное замещение", (r"времен\w*\s+замещен", r"замещен\w*")),
    ("Общение единомышленников", (r"единомышлен\w*", r"сообществ\w*")),
    ("Управление идеями", (r"управлен\w*\s+иде", r"иде\w*")),
    ("Адаптация", (r"адаптац\w*", r"анкет\w*")),
    ("Верхняя панель навигации", (r"верхн\w*\s+панел\w*", r"навигац\w*")),
    ("Баннеры", (r"баннер\w*",)),
    ("Геймификация", (r"геймификац\w*",)),
    ("Подбор", (r"подбор\w*", r"найм\w*")),
    ("Проекты", (r"проект\w*", r"функци\w*", r"интерес\w*")),
    ("Отчётность", (r"отч[её]т\w*", r"отч[её]тност\w*")),
    ("Административные настройки", (
        r"административ\w*", r"суперадмин\w*", r"настройк\w*",
        r"прав\w*\s+доступ", r"роль\w*\s+админ",
    )),
)

_COMPILED = tuple(
    (name, tuple(re.compile(pattern, _WORD) for pattern in patterns))
    for name, patterns in FTT_RULES
)

UNDEFINED = "Не определён"
TERMINAL = frozenset({5, 6})
IN_PROGRESS = 2
MSK = timezone(timedelta(hours=3))

# Производственный календарь РФ на 2026 год, пятидневная неделя.
CALENDAR = {
    "year": 2026,
    "timezone": "Europe/Moscow",
    "weekPattern": "monday-friday",
    "dailyHours": 8,
    "shortenedDays": {
        "2026-04-30": 7,
        "2026-05-08": 7,
        "2026-06-11": 7,
        "2026-11-03": 7,
    },
    "nonWorkingDates": (
        "2026-01-01", "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
        "2026-01-08", "2026-01-09", "2026-02-23", "2026-03-09", "2026-05-01",
        "2026-05-11", "2026-06-12", "2026-11-04", "2026-12-31",
    ),
}

_OFF = frozenset(CALENDAR["nonWorkingDates"])
_SHORT = CALENDAR["shortenedDays"]


def ftt_section(subject: str, description: str) -> str:
    """Раздел с наибольшим числом совпавших слов. При равенстве берётся более ранний."""
    text = f"{subject or ''}\n{description or ''}".lower().replace("ё", "е")
    best_score = 0
    best = UNDEFINED
    for name, patterns in _COMPILED:
        score = sum(1 for pattern in patterns if pattern.search(text))
        if score > best_score:
            best_score = score
            best = name
    return best


def _parse(value: str) -> datetime:
    moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _parts(value: str) -> dict[str, str]:
    local = _parse(value).astimezone(MSK)
    return {"date": local.strftime("%Y-%m-%d"), "time": local.strftime("%H:%M:%S")}


def _at(day: str, clock: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{clock}+03:00")


def _next_day(day: str) -> str:
    origin = datetime.fromisoformat(day + "T12:00:00+03:00")
    return (origin + timedelta(days=1)).astimezone(timezone.utc).strftime("%Y-%m-%d")


def _day_hours(day: str) -> int:
    noon = datetime.fromisoformat(day + "T12:00:00+03:00")
    if noon.weekday() >= 5 or day in _OFF:
        return 0
    return int(_SHORT.get(day) or CALENDAR["dailyHours"])


def work_hours_between(start: str | None, end: str | None) -> float | None:
    """Рабочие часы между двумя моментами: 09-13 и 14 до конца дня, без выходных."""
    if not start or not end:
        return None
    begin = _parse(start)
    finish = _parse(end)
    if not (finish > begin):
        return 0
    total = 0.0
    day = _parts(start)["date"]
    last = _parts(end)["date"]
    guard = 0
    while guard < 5000 and day <= last:
        hours = _day_hours(day)
        if hours:
            end_hour = 17 if hours < 8 else 18
            blocks = (
                (_at(day, "09:00:00"), _at(day, "13:00:00")),
                (_at(day, "14:00:00"), _at(day, f"{end_hour:02d}:00:00")),
            )
            for left, right in blocks:
                span = min(finish, right) - max(begin, left)
                total += max(0.0, span.total_seconds()) / 3600
        day = _next_day(day)
        guard += 1
    return math.floor(total * 100 + 0.5) / 100


def _status_id(issue: dict) -> int:
    raw = (issue.get("status") or {}).get("id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _first_status(issue: dict, ids: frozenset[int] | set[int]) -> str | None:
    found = []
    for journal in issue.get("journals") or []:
        for detail in journal.get("details") or []:
            if detail.get("property") != "attr" or detail.get("name") != "status_id":
                continue
            try:
                new_id = int(detail.get("new_value"))
            except (TypeError, ValueError):
                continue
            if new_id in ids and journal.get("created_on"):
                found.append(str(journal["created_on"]))
    return sorted(found)[0] if found else None


def cycle_hours(issue: dict) -> float | None:
    """Часы от первого «В работе» до закрытия. Пока задача открыта, часов нет."""
    start = _first_status(issue, {IN_PROGRESS})
    if not start and issue.get("start_date"):
        created = issue.get("created_on")
        clock = _parts(created)["time"] if created else "09:00:00"
        start = f"{issue['start_date']}T{clock}+03:00"
    if _status_id(issue) not in TERMINAL:
        return None
    end = _first_status(issue, TERMINAL) or issue.get("closed_on") or issue.get("updated_on")
    return work_hours_between(start, end)
