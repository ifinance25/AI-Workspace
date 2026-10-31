"""Таблицы ручной валидации находок прогона (``architecture/46``).

Имена ``office_test_runs`` и ``office_check_findings`` не заняты намеренно: их
создаст таск 34 со своим составом колонок. Журнал решений только дописывается,
UPDATE запрещён триггером. DELETE разрешён: иначе каскад удаления проекта упал бы.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS office_validation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES office_projects(id) ON DELETE CASCADE,
    run_key TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    schema_version INTEGER NOT NULL,
    package_sha TEXT NOT NULL,
    stand_version TEXT,
    imported_by INTEGER NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE (project_id, run_key)
);
CREATE TABLE IF NOT EXISTS office_validation_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES office_validation_runs(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES office_projects(id) ON DELETE CASCADE,
    gid TEXT NOT NULL,
    source_id TEXT NOT NULL DEFAULT '',
    defect_class TEXT NOT NULL DEFAULT 'document_defect',
    doc TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    severity_raw TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'hint',
    reason_key TEXT NOT NULL,
    llm_verdict TEXT NOT NULL DEFAULT '',
    llm_verdict_reason TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'new',
    lifecycle TEXT NOT NULL DEFAULT 'new',
    decision_seq INTEGER NOT NULL DEFAULT 0,
    rendered_seq INTEGER NOT NULL DEFAULT -1,
    scenario_id INTEGER,
    scenario_revision INTEGER,
    step_id TEXT,
    failure_key TEXT,
    task_id INTEGER,
    check_finding_id INTEGER,
    UNIQUE (run_id, gid),
    UNIQUE (run_id, reason_key)
);
CREATE INDEX IF NOT EXISTS ix_office_validation_findings_status
    ON office_validation_findings (run_id, review_status);
CREATE TABLE IF NOT EXISTS office_validation_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES office_validation_findings(id) ON DELETE CASCADE,
    run_id INTEGER NOT NULL REFERENCES office_validation_runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    decision_key TEXT NOT NULL,
    action TEXT NOT NULL,
    review_from TEXT NOT NULL,
    review_to TEXT NOT NULL,
    lifecycle_from TEXT NOT NULL,
    lifecycle_to TEXT NOT NULL,
    reason_code TEXT NOT NULL DEFAULT '',
    why TEXT NOT NULL,
    actor_id INTEGER NOT NULL,
    actor_role TEXT NOT NULL,
    request_key TEXT NOT NULL,
    at TEXT NOT NULL,
    prev_sha TEXT NOT NULL,
    entry_sha TEXT NOT NULL,
    UNIQUE (finding_id, seq),
    UNIQUE (finding_id, request_key)
);
CREATE TRIGGER IF NOT EXISTS tr_office_validation_decisions_no_update
BEFORE UPDATE ON office_validation_decisions
BEGIN
    SELECT RAISE(ABORT, 'журнал решений только дописывается');
END;
CREATE TABLE IF NOT EXISTS office_validation_edits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL REFERENCES office_validation_findings(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    edit_key TEXT NOT NULL,
    doc TEXT NOT NULL DEFAULT '',
    block TEXT NOT NULL DEFAULT '',
    col TEXT NOT NULL DEFAULT '',
    place TEXT NOT NULL DEFAULT '',
    old_text TEXT NOT NULL DEFAULT '',
    new_text TEXT NOT NULL DEFAULT '',
    comment TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'proposed',
    doc_ref TEXT NOT NULL DEFAULT '',
    applied_by INTEGER,
    applied_at TEXT,
    UNIQUE (finding_id, ordinal)
);
CREATE TABLE IF NOT EXISTS office_validation_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES office_validation_runs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    mime TEXT NOT NULL,
    UNIQUE (run_id, kind, name)
);
CREATE TABLE IF NOT EXISTS office_validation_policy (
    project_id INTEGER PRIMARY KEY REFERENCES office_projects(id) ON DELETE CASCADE,
    export_ban TEXT NOT NULL DEFAULT 'all_external',
    updated_by INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS office_validation_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES office_validation_runs(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL,
    at TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    files INTEGER NOT NULL
);
"""


class ValidationError(Exception):
    """Отказ валидации. ``code`` читает роутер, текст видит человек."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def ensure(store: Any) -> None:
    """Создать таблицы один раз на хранилище."""
    if getattr(store, "_validation_ready", False):
        return
    with store._lock:
        conn = store._connection()
        conn.executescript(_SCHEMA)
        conn.commit()
        store._validation_ready = True


def data_root(store: Any) -> Path:
    """Каталог файлов валидации рядом с базой, вне папок проектов панели."""
    return Path(store._path).parent / "office_validation"


def run_dir(store: Any, project_id: int, run_id: int) -> Path:
    return data_root(store) / f"p{int(project_id)}" / f"r{int(run_id)}"
