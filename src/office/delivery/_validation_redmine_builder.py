"""Сборка задачи Redmine для находки прогона (шаблон v6, Textile).

Канон: ``docs/redmine/Шаблон_тикета_Redmine.md`` (``REDMINE_TICKET_TEMPLATE_PATH``).
Поля API выровнены с ``import_20261022/build_and_publish.py``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.office.redmine_mirror._rules import ftt_section

REDMINE_TICKET_TEMPLATE_VERSION = 6
REDMINE_TICKET_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "redmine" / "Шаблон_тикета_Redmine.md"
)

# Идентификаторы полей Redmine (пилот HR-платформа, build_and_publish.py).
TRACKER_ERRORS = 1
STATUS_NEW = 1
PRIORITY_BY_SEVERITY = {"blocking": 4, "significant": 2, "hint": 1}
CF_TYPE = 4
CF_ENV = 7
CF_DEVICE = 25
CF_PAGE_URL = 15
CF_PLACEHOLDER_34 = 34
CF_PLACEHOLDER_35 = 35

_FAIL_FILL = "{background:#fdecec}. "
_MSK = timezone(timedelta(hours=3))


def _cell(text: str) -> str:
    return str(text or "").replace("|", "/").replace("\n", " ")


def _section_prefix(finding: dict) -> str:
    explicit = str(finding.get("section") or "").strip()
    if explicit:
        head = explicit.split(":", 1)[0].strip()
        return head or explicit
    return ftt_section(
        f"{finding.get('category') or ''} {finding.get('summary') or ''}",
        "",
    )


def build_subject(finding: dict) -> str:
    """Тема: «Раздел ФТТ>: краткая формулировка» (без gid в скобках)."""
    summary = str(finding.get("summary") or "").strip()
    prefix = _section_prefix(finding)
    if prefix and prefix != "Не определён":
        body = summary if summary else finding.get("gid") or "дефект"
        subject = f"{prefix}: {body}"
    else:
        subject = summary or str(finding.get("gid") or "дефект")
    return subject[:255]


def _priority_id(finding: dict) -> int:
    raw = str(finding.get("severity_raw") or finding.get("severity") or "").strip()
    if raw in PRIORITY_BY_SEVERITY:
        return PRIORITY_BY_SEVERITY[raw]
    ru = {"высокая": 4, "средняя": 2, "низкая": 1}
    return ru.get(raw, 2)


def _issue_type(finding: dict) -> str:
    explicit = str(finding.get("issue_type") or finding.get("type") or "").strip()
    if explicit:
        return explicit
    if finding.get("defect_class") == "document_defect":
        return "Документ"
    return "Frontend"


def _page_url(finding: dict) -> str:
    for key in ("page_url", "url", "stand_url"):
        value = str(finding.get(key) or "").strip()
        if value:
            return value
    for ref in finding.get("refs") or []:
        if isinstance(ref, dict):
            value = str(ref.get("url") or ref.get("page_url") or "").strip()
            if value:
                return value
    return ""


def _environment(finding: dict) -> list[str]:
    env = finding.get("environment") or finding.get("env")
    if isinstance(env, str) and env.strip():
        return [env.strip()]
    if isinstance(env, list) and env:
        return [str(v) for v in env]
    return ["dev"]


def _device(finding: dict) -> list[str]:
    device = finding.get("device") or finding.get("environment_device")
    if isinstance(device, str) and device.strip():
        return [device.strip()]
    if isinstance(device, list) and device:
        return [str(v) for v in device]
    return ["Десктоп"]


def _preconditions(finding: dict) -> list[str]:
    for key in ("pre", "preconditions"):
        raw = finding.get(key)
        if isinstance(raw, list) and raw:
            return [str(line).strip() for line in raw if str(line).strip()]
    role = str(finding.get("role") or "пользователь").strip()
    role_id = str(finding.get("role_id") or "").strip()
    login = str(finding.get("login") or "<логин>").strip()
    role_bit = f"роль «{role}»"
    if role_id:
        role_bit += f" ({role_id})"
    role_bit += f", логин {login};"
    lines = [role_bit]
    if finding.get("defect_class") == "stand_defect":
        lines.append("стенд доступен, учётная запись активна;")
    else:
        doc = str(finding.get("doc") or "документ").strip()
        lines.append(f"открыт документ «{doc}» для сверки;")
    why = str(finding.get("why") or "").strip()
    if why:
        lines.append(why)
    return lines


def _parse_step(item: Any) -> tuple[str, str, str, bool]:
    if isinstance(item, dict):
        actual = str(item.get("actual") or item.get("fact") or "")
        fail = bool(item.get("fail"))
        if actual.startswith("!"):
            fail = True
            actual = actual[1:].strip()
        return (
            str(item.get("action") or item.get("step") or ""),
            str(item.get("expected") or item.get("expect") or ""),
            actual,
            fail,
        )
    if isinstance(item, (list, tuple)) and len(item) >= 3:
        actual = str(item[2])
        fail = actual.startswith("!")
        if fail:
            actual = actual[1:].strip()
        expected = str(item[1]) if len(item) > 1 else ""
        action = str(item[0])
        return action, expected, actual, fail
    return str(item), "", "", False


def _steps(finding: dict) -> list[tuple[str, str, str, bool]]:
    raw = finding.get("steps")
    if isinstance(raw, list) and raw:
        return [_parse_step(item) for item in raw]
    summary = str(finding.get("summary") or "").strip()
    category = str(finding.get("category") or "проверка").strip()
    quote = ""
    for entry in finding.get("evidence") or []:
        if isinstance(entry, dict) and entry.get("quote"):
            quote = str(entry["quote"]).strip()
            break
    fact = quote or summary or "Нарушение зафиксировано при сверке."
    if summary:
        return [
            (category, "Соответствует ожидаемому.", "Соответствует ожидаемому.", False),
            (summary, "Соответствует требованию документа.", fact, True),
        ]
    return [(category, "Соответствует ожидаемому.", fact, True)]


def _requirements(finding: dict) -> list[str]:
    lines: list[str] = []
    for clause in finding.get("clauses") or []:
        text = str(clause).strip()
        if text:
            lines.append(text if text.startswith("*") else f"* {text.lstrip('* ')}")
    for scenario in finding.get("scenarios") or []:
        text = str(scenario).strip()
        if text:
            lines.append(f"* {text}" if not text.startswith("*") else text)
    if not lines:
        doc = str(finding.get("doc") or "").strip()
        if doc:
            lines.append(f"* Документ «{doc}», категория «{finding.get('category') or ''}».")
    return lines


def _acceptance(finding: dict) -> list[str]:
    for key in ("acceptance", "crit", "acceptance_criteria"):
        raw = finding.get(key)
        if isinstance(raw, list) and raw:
            return [str(line).strip() for line in raw if str(line).strip()]
    summary = str(finding.get("summary") or "").strip()
    if summary:
        return [
            f"После исправления: {summary}",
            "Повторная проверка по сценарию из ПМИ проходит без расхождений.",
        ]
    return ["Дефект устранён, фактический результат совпадает с ожидаемым."]


def _evidence_rows(
    finding: dict,
    attachment_names: list[str],
) -> tuple[list[str], bool]:
    """Строки таблицы «Доказательства» и флаг «есть вложения»."""
    rows: list[str] = []
    marked = finding.get("marked") or []
    evidence = finding.get("evidence") or []
    labels: list[tuple[str, str]] = []
    for entry in marked:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("img") or entry.get("name") or "").strip()
        if not name:
            continue
        label = str(entry.get("label") or "Как сейчас на стенде:").strip()
        labels.append((label, Path(name).name))
    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("img") or "").strip()
        if not name or any(name.endswith(Path(n).name) or n == name for _, n in labels):
            continue
        doc = str(entry.get("doc") or finding.get("doc") or "").strip()
        page = entry.get("page")
        page_bit = f", с. {page}" if page else ""
        label = f"Снимок ({doc}{page_bit}):"
        labels.append((label, Path(name).name))
    if not labels and attachment_names:
        for name in attachment_names:
            labels.append(("Как сейчас на стенде:", Path(name).name))
    if labels:
        lines = [
            "table{background:#ffffff}.",
            "|_{background:#eeeeee}. Доказательства |",
            "| Сравниваемая область обведена красной рамкой. |",
        ]
        for label, filename in labels:
            lines.append(
                f"| {label} {{{{collapse(скриншот) !{filename}! }}}} |"
            )
        return lines, True
    note = str(finding.get("evidence_note") or "").strip()
    if not note:
        for entry in evidence:
            if isinstance(entry, dict) and entry.get("quote"):
                note = f"Цитата: «{entry['quote']}»"
                break
    if not note:
        note = "Снимок приложен отдельно или недоступен в пакете прогона."
    return ["*Доказательства:*", note[:1].upper() + note[1:] if note else note], False


def _observed_at(finding: dict, run_meta: dict) -> str:
    for row in reversed(finding.get("history") or []):
        if row.get("review_to") == "confirmed" and row.get("at"):
            return _format_msk(str(row["at"]))
    for key in ("observed_at", "at"):
        value = finding.get(key)
        if value:
            return _format_msk(str(value))
    imported = str(run_meta.get("imported_at") or "").strip()
    if imported:
        return _format_msk(imported)
    return _format_msk(datetime.now(timezone.utc).isoformat())


def _format_msk(raw: str) -> str:
    moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(_MSK)
    return local.strftime("%d.%m.%Y %H:%M") + " МСК"


def build_description(
    finding: dict,
    *,
    run_key: str,
    attachment_names: list[str] | None = None,
    run_meta: dict | None = None,
) -> str:
    """Описание строго в порядке разделов шаблона v6 (Textile)."""
    run_meta = run_meta or {}
    names = attachment_names or []
    lines: list[str] = ["*Предусловия:*"]
    lines.extend(f"* {line}" for line in _preconditions(finding))
    lines.extend(["", "*Шаги воспроизведения:*", "", "table{background:#ffffff}."])
    lines.append(
        "|_. Шаг |_. Действие |_. Ожидаемый результат |_. Фактический результат |"
    )
    for index, (action, expected, actual, fail) in enumerate(_steps(finding), 1):
        fact = actual or ("Соответствует ожидаемому." if not fail else "")
        prefix = _FAIL_FILL if fail else " "
        lines.append(
            f"| {index} | {_cell(action)} | {_cell(expected)} |{prefix}{_cell(fact)} |"
        )
    lines.extend(["", "*Требование:*"])
    for req in _requirements(finding):
        lines.append(req if req.startswith("*") else f"* {req}")
    lines.extend(["", "*Критерии приёмки:*"])
    for crit in _acceptance(finding):
        lines.append(f"* {crit.lstrip('* ')}")
    lines.append("")
    evidence_block, _ = _evidence_rows(finding, names)
    lines.extend(evidence_block)
    gid = finding.get("gid") or ""
    source_id = str(finding.get("source_id") or "").strip()
    src_label = gid
    if source_id:
        src_label = f"{gid} ({source_id})"
    observed = _observed_at(finding, run_meta)
    lines.extend(["", "---", "", f"*Источник:* валидация {src_label}, прогон {run_key}, {observed}."])
    return "\n".join(lines).strip() + "\n"


def build_issue_fields(
    finding: dict,
    *,
    run_key: str,
    attachment_names: list[str] | None = None,
    run_meta: dict | None = None,
) -> dict[str, Any]:
    """Поля POST /issues.json без project_id (его подставляет HttpRedmine)."""
    return {
        "tracker_id": int(finding.get("tracker_id") or TRACKER_ERRORS),
        "status_id": STATUS_NEW,
        "priority_id": int(finding.get("priority_id") or _priority_id(finding)),
        "subject": build_subject(finding),
        "description": build_description(
            finding,
            run_key=run_key,
            attachment_names=attachment_names,
            run_meta=run_meta,
        ),
        "custom_fields": [
            {"id": CF_TYPE, "value": _issue_type(finding)},
            {"id": CF_ENV, "value": _environment(finding)},
            {"id": CF_DEVICE, "value": _device(finding)},
            {"id": CF_PAGE_URL, "value": _page_url(finding)},
            {"id": CF_PLACEHOLDER_34, "value": ""},
            {"id": CF_PLACEHOLDER_35, "value": ""},
        ],
    }


def related_issue_ids(finding: dict) -> list[int]:
    ids: list[int] = []
    for raw in finding.get("redmine") or []:
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        if number not in ids:
            ids.append(number)
    for raw in finding.get("related") or []:
        text = str(raw).strip().lstrip("#")
        if text.isdigit():
            number = int(text)
            if number not in ids:
                ids.append(number)
    return ids
