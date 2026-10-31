"""Решения проверяющего: транзакция в базе, журнал только на дописывание.

Источник правды это база. Файлы пишутся уже после фиксации, их сбой решения не
отменяет. ``expected_seq`` ловит одновременную правку, ``request_key`` двойное
нажатие.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from src.office.delivery._scan import scan
from src.office.delivery._validation_files import sync_files
from src.office.delivery._validation_lifecycle import (
    ACTIONS,
    DEFAULT_WHY,
    REASON_CODES,
    assert_allowed,
    plan_steps,
)
from src.office.delivery._validation_schema import ValidationError, ensure

_MSK = timedelta(hours=3)
_WHY_REQUIRED = frozenset({"reject", "clarify"})
_MAX_WHY = 2000
_MAX_DOC_REF = 300


def entry_hash(prev_sha: str, entry: dict) -> str:
    """Отпечаток записи журнала: подмена прошлой строки ломает цепочку."""
    raw = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(f"{prev_sha}|{raw}".encode("utf-8")).hexdigest()


def _normalize(action: str, why: str, reason_code: str, doc_ref: str) -> tuple[str, str, str]:
    if action not in ACTIONS:
        raise ValidationError("bad_input", "Неизвестное действие")
    text = (why or "").strip()
    ref = (doc_ref or "").strip()
    if action in _WHY_REQUIRED and not text:
        raise ValidationError("bad_input", "Укажите причину")
    if action == "reject" and reason_code not in REASON_CODES:
        raise ValidationError("bad_input", "Выберите причину отклонения")
    if reason_code and reason_code not in REASON_CODES:
        raise ValidationError("bad_input", "Неизвестная причина")
    if action == "edits_applied" and not ref:
        raise ValidationError("bad_input", "Укажите версию документа с правками")
    if len(text) > _MAX_WHY or len(ref) > _MAX_DOC_REF:
        raise ValidationError("bad_input", "Текст слишком длинный")
    hits = scan(f"{text}\n{ref}")
    if hits:
        raise ValidationError("scan_failed", f"В тексте есть запрещённые данные: {', '.join(hits)}")
    return text or DEFAULT_WHY.get(action, ""), reason_code, ref


def _finding(conn: Any, project_id: int, run_id: int, finding_id: int) -> Any:
    row = conn.execute(
        "SELECT * FROM office_validation_findings WHERE id = ? AND run_id = ? AND project_id = ?",
        (finding_id, run_id, project_id),
    ).fetchone()
    if row is None:
        raise ValidationError("not_found", "Находка не найдена")
    return row


def _next_key(conn: Any, project_id: int, moment: datetime) -> str:
    day = (moment + _MSK).strftime("%Y%m%d")
    count = conn.execute(
        "SELECT COUNT(*) FROM office_validation_decisions d "
        "JOIN office_validation_runs r ON r.id = d.run_id "
        "WHERE r.project_id = ? AND d.decision_key LIKE ?",
        (project_id, f"DEC-{day}-%"),
    ).fetchone()[0]
    return f"DEC-{day}-{count + 1:03d}"


def _append(conn: Any, row: Any, project_id: int, step: tuple[str, str], fields: dict) -> None:
    review_from, lifecycle_from, seq = row
    review_to, lifecycle_to = step
    assert_allowed(lifecycle_from, lifecycle_to)
    prev = conn.execute(
        "SELECT entry_sha FROM office_validation_decisions WHERE run_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (fields["run_id"],),
    ).fetchone()
    prev_sha = prev["entry_sha"] if prev else ""
    entry = {
        **fields,
        "seq": seq + 1,
        "decision_key": _next_key(conn, project_id, fields["moment"]),
        "review_from": review_from,
        "review_to": review_to,
        "lifecycle_from": lifecycle_from,
        "lifecycle_to": lifecycle_to,
    }
    del entry["moment"]
    conn.execute(
        "INSERT INTO office_validation_decisions (finding_id, run_id, seq, decision_key, action, "
        "review_from, review_to, lifecycle_from, lifecycle_to, reason_code, why, actor_id, "
        "actor_role, request_key, at, prev_sha, entry_sha) "
        "VALUES (:finding_id, :run_id, :seq, :decision_key, :action, :review_from, :review_to, "
        ":lifecycle_from, :lifecycle_to, :reason_code, :why, :actor_id, :actor_role, "
        ":request_key, :at, :prev_sha, :entry_sha)",
        {**entry, "prev_sha": prev_sha, "entry_sha": entry_hash(prev_sha, entry)},
    )


def _apply_edits(conn: Any, finding_id: int, action: str, ctx: dict) -> None:
    if action == "confirm":
        conn.execute(
            "UPDATE office_validation_edits SET state = 'queued' "
            "WHERE finding_id = ? AND state IN ('proposed', 'rejected')",
            (finding_id,),
        )
    elif action == "reject":
        conn.execute(
            "UPDATE office_validation_edits SET state = 'rejected' WHERE finding_id = ?",
            (finding_id,),
        )
    elif action == "edits_applied":
        conn.execute(
            "UPDATE office_validation_edits SET state = 'applied', doc_ref = ?, applied_by = ?, "
            "applied_at = ? WHERE finding_id = ? AND state = 'queued'",
            (ctx["doc_ref"], ctx["actor_id"], ctx["at"], finding_id),
        )
    elif action == "reopen":
        conn.execute(
            "UPDATE office_validation_edits SET state = 'queued', doc_ref = '', applied_by = NULL, "
            "applied_at = NULL WHERE finding_id = ? AND state = 'applied'",
            (finding_id,),
        )


def _decide_tx(conn: Any, project_id: int, row: Any, data: dict) -> None:
    steps = plan_steps(data["action"], row["review_status"], row["lifecycle"])
    state = (row["review_status"], row["lifecycle"], row["decision_seq"])
    for number, step in enumerate(steps):
        key = data["request_key"] if number == 0 else f"{data['request_key']}:{number + 1}"
        _append(conn, state, project_id, step, {
            "finding_id": row["id"], "run_id": row["run_id"], "action": data["action"],
            "reason_code": data["reason_code"], "why": data["why"], "actor_id": data["actor_id"],
            "actor_role": data["actor_role"], "request_key": key, "at": data["at"],
            "moment": data["moment"],
        })
        state = (step[0], step[1], state[2] + 1)
    _apply_edits(conn, row["id"], data["action"], data)
    conn.execute(
        "UPDATE office_validation_findings SET review_status = ?, lifecycle = ?, decision_seq = ? "
        "WHERE id = ?",
        (state[0], state[1], state[2], row["id"]),
    )


def decide(
    store: Any, project_id: int, run_id: int, finding_id: int, *, action: str, actor_id: int,
    actor_role: str, expected_seq: int, request_key: str, why: str = "", reason_code: str = "",
    doc_ref: str = "", now: datetime | None = None,
) -> dict:
    """Записать решение. Ответ содержит состояние и признак ``files_stale``."""
    ensure(store)
    text, code, ref = _normalize(action, why, reason_code, doc_ref)
    key = (request_key or "").strip()
    if not key or len(key) > 80:
        raise ValidationError("bad_input", "Нужен ключ запроса")
    moment = now or datetime.now(timezone.utc)
    with store._lock:
        conn = store._connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = _finding(conn, project_id, run_id, finding_id)
            repeated = conn.execute(
                "SELECT 1 FROM office_validation_decisions "
                "WHERE finding_id = ? AND request_key = ?",
                (finding_id, key),
            ).fetchone()
            if repeated is None:
                if row["decision_seq"] != expected_seq:
                    raise ValidationError("stale", "Находку уже изменил другой проверяющий")
                _decide_tx(conn, project_id, row, {
                    "action": action, "why": text, "reason_code": code, "doc_ref": ref,
                    "actor_id": actor_id, "actor_role": actor_role, "request_key": key,
                    "moment": moment, "at": moment.isoformat(timespec="seconds"),
                })
            conn.commit()
            row = _finding(conn, project_id, run_id, finding_id)
        except Exception:
            conn.rollback()
            raise
    return {
        "finding_id": finding_id,
        "review_status": row["review_status"],
        "lifecycle": row["lifecycle"],
        "decision_seq": row["decision_seq"],
        "files_stale": not sync_files(store, project_id, run_id),
    }
