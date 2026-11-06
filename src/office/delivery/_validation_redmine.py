"""Выгрузка подтверждённой находки в Redmine ключом проверяющего (один запрос).

Токен не пишется в журнал и не сохраняется на сервере: только проверка и вызов API.
Адрес и проект берутся из учётной записи платформы (``office_redmine_account``).
Описание и поля задачи собираются по ``docs/redmine/Шаблон_тикета_Redmine.md`` (v6).
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.office.delivery._validation_read import asset_path, get_finding
from src.office.delivery._validation_redmine_builder import (
    REDMINE_TICKET_TEMPLATE_PATH,
    build_issue_fields,
    build_subject,
    related_issue_ids,
)
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


def _run_meta(store: Any, project_id: int, run_id: int) -> dict:
    with store._lock:
        row = store._connection().execute(
            "SELECT run_key, title, source_kind, stand_version, imported_at "
            "FROM office_validation_runs WHERE id = ? AND project_id = ?",
            (run_id, project_id),
        ).fetchone()
    if row is None:
        raise ValidationError("not_found", "Прогон не найден")
    return dict(row)


def _duplicate_in_mirror(store: Any, project_id: int, subject: str) -> int | None:
    """Поиск дубля по теме в локальном зеркале (шаблон §75, без полной выгрузки Redmine)."""
    _ensure_redmine_tables(store)
    target = subject.strip()
    if not target:
        return None
    with store._lock:
        rows = store._connection().execute(
            "SELECT issue_id, payload FROM office_redmine_issues WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except json.JSONDecodeError:
            continue
        if str(payload.get("subject") or "").strip() == target:
            return int(row["issue_id"])
    return None


def _attachment_sources(finding: dict) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for key in ("marked", "evidence"):
        for entry in finding.get(key) or []:
            if not isinstance(entry, dict):
                continue
            asset_id = entry.get("asset_id")
            img = str(entry.get("img") or "").strip()
            if asset_id is None or not img or img in seen:
                continue
            seen.add(img)
            out.append(entry)
    return out


def _upload_attachments(
    client: HttpRedmine,
    store: Any,
    project_id: int,
    run_id: int,
    finding: dict,
) -> tuple[list[dict], list[str]]:
    uploads: list[dict] = []
    names: list[str] = []
    for entry in _attachment_sources(finding):
        path, name, mime = asset_path(store, project_id, run_id, int(entry["asset_id"]))
        token = client.upload_attachment(path, name)
        uploads.append({"token": token, "filename": name, "content_type": mime or "image/png"})
        names.append(name)
    return uploads, names


def _apply_relations(client: HttpRedmine, issue_id: int, related: list[int]) -> None:
    for other in related:
        if other == issue_id:
            continue
        try:
            client.create_relation(issue_id, other, "relates")
        except RedmineUnavailableError:
            # TODO по шаблону §77-80: при недостаточных правах API связи ставятся вручную relations.py
            continue


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
    if not REDMINE_TICKET_TEMPLATE_PATH.is_file():
        raise ValidationError("bad_input", "В репозитории нет шаблона Redmine (docs/redmine/)")
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

    run_meta = _run_meta(store, project_id, run_id)
    subject = build_subject(finding)
    duplicate = _duplicate_in_mirror(store, project_id, subject)
    if duplicate is not None:
        raise ValidationError(
            "bad_input",
            f"Задача с такой темой уже есть в зеркале Redmine (#{duplicate}). "
            "По шаблону v6 дубль не создаём.",
        )

    client = HttpRedmine(base_url, token)
    try:
        uploads, names = _upload_attachments(client, store, project_id, run_id, finding)
    except RedmineUnavailableError as exc:
        raise ValidationError("bad_input", "Redmine не принял вложение") from exc

    fields = build_issue_fields(
        finding,
        run_key=str(run_meta["run_key"]),
        attachment_names=names,
        run_meta=run_meta,
    )
    if uploads:
        fields["uploads"] = uploads

    try:
        created = client.create_issue(redmine_project, fields)
    except RedmineUnavailableError as exc:
        raise ValidationError("bad_input", "Redmine не принял создание задачи") from exc
    raw = created.get("issue") if isinstance(created, dict) else None
    if not isinstance(raw, dict) or raw.get("id") is None:
        raise ValidationError("bad_input", "Redmine не вернул номер задачи")
    issue_id = int(raw["id"])
    issue_url = f"{base_url}/issues/{issue_id}"

    related = [rid for rid in related_issue_ids(finding) if rid != issue_id]
    if related:
        _apply_relations(client, issue_id, related)

    with store._lock:
        conn = store._connection()
        conn.execute(
            "INSERT INTO office_redmine_creates (project_id, request_key, issue_id) VALUES (?, ?, ?)",
            (project_id, request_key, issue_id),
        )
        conn.commit()
    _persist_link(store, finding_id, issue_id, issue_url)
    return {"issue_id": issue_id, "issue_url": issue_url, "created": True}
