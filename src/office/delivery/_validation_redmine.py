"""Выгрузка подтверждённой находки в Redmine ключом проверяющего (один запрос).

Токен не пишется в журнал и не сохраняется на сервере: только проверка и вызов API.
Адрес и проект берутся из учётной записи платформы (``office_redmine_account``).
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.office.delivery._validation_read import get_finding
from src.office.delivery._validation_schema import ValidationError, ensure
from src.office.redmine_mirror._account import _row
from src.office.redmine_mirror._http import HttpRedmine
from src.office.redmine_mirror._mirror import RedmineUnavailableError
from src.office.redmine_mirror._mirror import _ensure as _ensure_redmine_tables

_TOKEN = re.compile(r"^[A-Za-z0-9._-]{16,128}$")


def _normalize_token(raw: str) -> str:
    token = (raw or "").strip()
    if not _TOKEN.fullmatch(token):
        raise ValidationError("bad_input", "Формат ключа Redmine неверный")
    return token


def _settings(store: Any) -> tuple[str, str]:
    ensure(store)
    row = _row(store)
    base = (row.get("base_url") or "").rstrip("/")
    project = (row.get("redmine_project") or "").strip()
    if not base or not project:
        raise ValidationError("bad_input", "Redmine не настроен: админ задаёт адрес и проект")
    return base, project


def _verify_token(base_url: str, token: str) -> None:
    client = HttpRedmine(base_url, token)
    try:
        page = client._call("GET", "/users/current.json")
    except RedmineUnavailableError as exc:
        raise ValidationError("bad_input", "Redmine не принял ключ") from exc
    user = page.get("user")
    if not isinstance(user, dict) or not user.get("id"):
        raise ValidationError("bad_input", "Redmine не принял ключ")


def _description(finding: dict) -> str:
    lines = [
        f"Находка: {finding['gid']}",
        f"Документ: {finding['doc']}",
        "",
        "Суть:",
        finding.get("summary") or "",
        "",
    ]
    refs = finding.get("refs") or []
    if refs:
        ref = refs[0]
        page = ref.get("page")
        lines.append(f"Страница PDF: {ref.get('pdf') or finding['doc']}" + (f", стр. {page}" if page else ""))
    evidence = finding.get("evidence") or []
    if evidence:
        quote = evidence[0].get("quote")
        if quote:
            lines.extend(["", "Цитата:", f"«{quote}»"])
    edits = finding.get("edits") or []
    if edits:
        lines.append("")
        lines.append("Правки (было → стало):")
        for edit in edits[:5]:
            old = edit.get("old_text") or "(пусто)"
            new = edit.get("new_text") or "(удалить)"
            place = edit.get("place") or edit.get("doc") or ""
            lines.append(f"- {place}: {old} → {new}")
    return "\n".join(lines).strip()


def _persist_link(store: Any, finding_id: int, issue_id: int, issue_url: str) -> None:
    with store._lock:
        conn = store._connection()
        row = conn.execute(
            "SELECT payload FROM office_validation_findings WHERE id = ?", (finding_id,)
        ).fetchone()
        if row is None:
            raise ValidationError("not_found", "Находка не найдена")
        payload = json.loads(row["payload"])
        numbers = list(payload.get("redmine") or [])
        links = list(payload.get("redmine_links") or [])
        if issue_id not in numbers:
            numbers.append(issue_id)
        if issue_url not in links:
            links.append(issue_url)
        payload["redmine"] = numbers
        payload["redmine_links"] = links
        conn.execute(
            "UPDATE office_validation_findings SET payload = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), finding_id),
        )
        conn.commit()


def _aggregate_stand_description(
    run_key: str, title: str, stand_version: str | None, findings: list[dict]
) -> str:
    lines = [
        f"Прогон: {run_key}",
        f"Название: {title or '—'}",
        f"Версия стенда: {stand_version or '—'}",
        "",
        "Подтверждённые дефекты стенда (исправление на стенде, не в документе):",
        "",
    ]
    for row in findings:
        payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        summary = str(payload.get("summary") or "").strip()
        lines.append(f"- {row['gid']} ({row['doc']}, {row['category']}): {summary}")
    lines.extend(["", f"Всего: {len(findings)}"])
    return "\n".join(lines)


def _confirmed_stand_findings(conn: Any, run_id: int) -> list[Any]:
    return conn.execute(
        "SELECT id, gid, doc, category, payload FROM office_validation_findings "
        "WHERE run_id = ? AND defect_class = 'stand_defect' AND review_status = 'confirmed' "
        "ORDER BY id",
        (run_id,),
    ).fetchall()


def export_run_stand_remediation(
    store: Any,
    project_id: int,
    run_id: int,
    *,
    api_key: str,
    request_key: str,
) -> dict:
    """Один сводный тикет Redmine на исправление стенда после закрытия прогона.

    Создаётся, когда прогон ``stand_run`` можно закрыть и есть подтверждённые
    ``stand_defect``. Повтор ``request_key`` не дублирует задачу.
    """
    if not str(request_key).strip():
        raise ValidationError("bad_input", "Нет ключа запроса")
    ensure(store)
    _ensure_redmine_tables(store)
    with store._lock:
        conn = store._connection()
        run = conn.execute(
            "SELECT run_key, source_kind, title, stand_version FROM office_validation_runs "
            "WHERE id = ? AND project_id = ?",
            (run_id, project_id),
        ).fetchone()
        if run is None:
            raise ValidationError("not_found", "Прогон не найден")
        if run["source_kind"] != "stand_run":
            raise ValidationError("bad_transition", "Сводный тикет только для прогона стенда")
        pending = conn.execute(
            "SELECT COUNT(*) FROM office_validation_findings WHERE run_id = ? "
            "AND review_status IN ('new', 'needs_info')",
            (run_id,),
        ).fetchone()[0]
        if pending:
            raise ValidationError(
                "bad_transition", "Сначала разберите все находки без решения и на уточнении"
            )
        rows = _confirmed_stand_findings(conn, run_id)
    if not rows:
        raise ValidationError("bad_transition", "Нет подтверждённых дефектов стенда для тикета")

    base_url, redmine_project = _settings(store)
    token = _normalize_token(api_key)
    _verify_token(base_url, token)
    dedupe_key = f"run-{run_id}-stand-remediation"

    with store._lock:
        dup = store._connection().execute(
            "SELECT issue_id FROM office_redmine_creates WHERE project_id = ? AND request_key = ?",
            (project_id, dedupe_key),
        ).fetchone()
    if dup is not None:
        issue_id = int(dup["issue_id"])
        url = f"{base_url}/issues/{issue_id}"
        for row in rows:
            _persist_link(store, int(row["id"]), issue_id, url)
        return {
            "issue_id": issue_id,
            "issue_url": url,
            "created": False,
            "findings": len(rows),
        }

    subject = f"Исправление стенда по прогону {run['run_key']}"[:255]
    description = _aggregate_stand_description(
        run["run_key"], run["title"], run["stand_version"], [dict(r) for r in rows]
    )
    client = HttpRedmine(base_url, token)
    try:
        created = client.create_issue(
            redmine_project,
            {"subject": subject, "description": description},
        )
    except RedmineUnavailableError as exc:
        raise ValidationError("bad_input", "Redmine не принял создание задачи") from exc
    raw = created.get("issue") if isinstance(created, dict) else None
    if not isinstance(raw, dict) or raw.get("id") is None:
        raise ValidationError("bad_input", "Redmine не вернул номер задачи")
    issue_id = int(raw["id"])
    issue_url = f"{base_url}/issues/{issue_id}"
    with store._lock:
        conn = store._connection()
        conn.execute(
            "INSERT INTO office_redmine_creates (project_id, request_key, issue_id) VALUES (?, ?, ?)",
            (project_id, dedupe_key, issue_id),
        )
        conn.commit()
    for row in rows:
        _persist_link(store, int(row["id"]), issue_id, issue_url)
    return {
        "issue_id": issue_id,
        "issue_url": issue_url,
        "created": True,
        "findings": len(rows),
    }


def export_finding_to_redmine(
    store: Any,
    project_id: int,
    run_id: int,
    finding_id: int,
    *,
    api_key: str,
    request_key: str,
) -> dict:
    """Создать задачу от имени владельца ключа. Повтор ``request_key`` не дублирует."""
    if not str(request_key).strip():
        raise ValidationError("bad_input", "Нет ключа запроса")
    ensure(store)
    _ensure_redmine_tables(store)
    finding = get_finding(store, project_id, run_id, finding_id)
    if finding["review_status"] != "confirmed":
        raise ValidationError("bad_transition", "Задачу в Redmine можно создать только для подтверждённого дефекта")
    base_url, redmine_project = _settings(store)
    token = _normalize_token(api_key)
    _verify_token(base_url, token)

    with store._lock:
        dup = store._connection().execute(
            "SELECT issue_id FROM office_redmine_creates WHERE project_id = ? AND request_key = ?",
            (project_id, request_key),
        ).fetchone()
    if dup is not None:
        issue_id = int(dup["issue_id"])
        url = f"{base_url}/issues/{issue_id}"
        _persist_link(store, finding_id, issue_id, url)
        return {"issue_id": issue_id, "issue_url": url, "created": False}

    subject = f"[{finding['gid']}] {(finding.get('summary') or '')[:120]}".strip()
    client = HttpRedmine(base_url, token)
    try:
        created = client.create_issue(
            redmine_project,
            {"subject": subject, "description": _description(finding)},
        )
    except RedmineUnavailableError as exc:
        raise ValidationError("bad_input", "Redmine не принял создание задачи") from exc
    raw = created.get("issue") if isinstance(created, dict) else None
    if not isinstance(raw, dict) or raw.get("id") is None:
        raise ValidationError("bad_input", "Redmine не вернул номер задачи")
    issue_id = int(raw["id"])
    issue_url = f"{base_url}/issues/{issue_id}"
    with store._lock:
        conn = store._connection()
        conn.execute(
            "INSERT INTO office_redmine_creates (project_id, request_key, issue_id) VALUES (?, ?, ?)",
            (project_id, request_key, issue_id),
        )
        conn.commit()
    _persist_link(store, finding_id, issue_id, issue_url)
    return {"issue_id": issue_id, "issue_url": issue_url, "created": True}
