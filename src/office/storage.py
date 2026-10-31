"""Хранилище проектного офиса: таблицы ``office_*`` в той же SQLite-базе, что и чаты.

Схема создаётся при старте идемпотентно (``CREATE TABLE IF NOT EXISTS``), поэтому
повторный запуск ничего не ломает. ``SessionManager`` не расширяется: офис держит
собственное соединение к тому же файлу (WAL + busy_timeout, как ``ApiKeyStore``).

Три сущности, на которые опираются паспорт, бриф и задание:
проект офиса (паспорт), участники с ролью, документ проекта и его версии Markdown.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

OFFICE_TABLES = (
    "office_projects",
    "office_members",
    "office_documents",
    "office_document_versions",
    "office_channel_bindings",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS office_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    work_kind TEXT NOT NULL DEFAULT '',
    nature TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    project_type TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    create_key TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS office_members (
    project_id INTEGER NOT NULL REFERENCES office_projects(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (project_id, user_id)
);
CREATE TABLE IF NOT EXISTS office_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES office_projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (project_id, kind)
);
CREATE TABLE IF NOT EXISTS office_document_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES office_documents(id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    source TEXT NOT NULL DEFAULT '',
    markdown TEXT NOT NULL DEFAULT '',
    created_by INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE (document_id, number)
);
CREATE TABLE IF NOT EXISTS office_channel_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    channel TEXT NOT NULL,
    external_user_id TEXT,
    external_username TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'pending',
    code_hash TEXT,
    code_expires_at REAL,
    confirm_expires_at REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_office_channel_bindings_user
    ON office_channel_bindings (user_id, channel) WHERE state = 'active';
CREATE UNIQUE INDEX IF NOT EXISTS ux_office_channel_bindings_external
    ON office_channel_bindings (channel, external_user_id) WHERE state = 'active';
CREATE INDEX IF NOT EXISTS ix_office_channel_bindings_code
    ON office_channel_bindings (code_hash);
"""

# Колонки паспорта, которые можно менять через update_project.
PASSPORT_FIELDS = ("name", "work_kind", "nature", "description", "project_type", "status")

# Колонки паспорта, добавленные после первой схемы: базе, созданной раньше,
# их докидывает ALTER TABLE при старте.
_ADDED_PROJECT_COLUMNS = {
    "description": "TEXT NOT NULL DEFAULT ''",
    "create_key": "TEXT",
}

# Ключ идемпотентности создания: повтор того же ключа тем же автором не
# создаёт второй проект. NULL в уникальном индексе SQLite не конфликтует.
_CREATE_KEY_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_office_projects_create_key "
    "ON office_projects (created_by, create_key)"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_channel_code(code: str) -> str:
    """Хэш одноразового кода привязки: сам код в базе не лежит."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class ChannelBindingConflictError(Exception):
    """Аккаунт мессенджера или учётка уже заняты активной привязкой."""


class OfficeStore:
    """Сырой доступ к таблицам офиса. Правила видимости и ролей живут в границах."""

    def __init__(self, db_path: str | Path):
        self._path = Path(db_path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._initialize_db()

    def _connection(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        conn = sqlite3.connect(self._path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        self._conn = conn
        return conn

    def _initialize_db(self) -> None:
        with self._lock:
            conn = self._connection()
            conn.executescript(_SCHEMA)
            have = {r["name"] for r in conn.execute("PRAGMA table_info(office_projects)")}
            for column, decl in _ADDED_PROJECT_COLUMNS.items():
                if column not in have:
                    conn.execute(f"ALTER TABLE office_projects ADD COLUMN {column} {decl}")
            conn.execute(_CREATE_KEY_INDEX)
            conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    # ------------------------------------------------------------------
    # Проекты (паспорт)
    # ------------------------------------------------------------------

    def create_project(
        self,
        *,
        name: str,
        created_by: int,
        work_kind: str = "",
        nature: str = "",
        description: str = "",
        project_type: str = "",
        status: str = "draft",
        create_key: str | None = None,
    ) -> dict:
        """Тип пустой, а проект черновик, пока человек не выбрал тип (таск 02).

        Повтор ``create_key`` тем же автором возвращает уже созданный проект.
        """
        now = _now()
        with self._lock:
            conn = self._connection()
            try:
                cur = conn.execute(
                    "INSERT INTO office_projects (name, work_kind, nature, description, "
                    "project_type, status, create_key, created_by, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, work_kind, nature, description, project_type, status, create_key,
                     created_by, now, now),
                )
            except sqlite3.IntegrityError:
                conn.rollback()
                row = conn.execute(
                    "SELECT id FROM office_projects WHERE created_by = ? AND create_key = ?",
                    (created_by, create_key),
                ).fetchone()
                if row is None:
                    raise
                project_id = int(row["id"])
            else:
                conn.commit()
                project_id = int(cur.lastrowid)
        project = self.get_project(project_id)
        assert project is not None
        return project

    def get_project(self, project_id: int) -> dict | None:
        with self._lock:
            row = self._connection().execute(
                "SELECT * FROM office_projects WHERE id = ?", (project_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_projects(self) -> list[dict]:
        with self._lock:
            rows = self._connection().execute(
                "SELECT * FROM office_projects ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def list_projects_for_user(self, user_id: int) -> list[dict]:
        """Проекты, где пользователь записан участником."""
        with self._lock:
            rows = self._connection().execute(
                "SELECT p.* FROM office_projects p "
                "JOIN office_members m ON m.project_id = p.id "
                "WHERE m.user_id = ? ORDER BY p.id",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_project(self, project_id: int, **fields: str) -> dict | None:
        """Меняет поля паспорта (см. ``PASSPORT_FIELDS``); чужие ключи отвергает."""
        unknown = set(fields) - set(PASSPORT_FIELDS)
        if unknown:
            raise ValueError(f"не поля паспорта: {sorted(unknown)}")
        if not fields:
            return self.get_project(project_id)
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self._lock:
            conn = self._connection()
            conn.execute(
                f"UPDATE office_projects SET {assignments}, updated_at = ? WHERE id = ?",
                (*fields.values(), _now(), project_id),
            )
            conn.commit()
        return self.get_project(project_id)

    def delete_project(self, project_id: int) -> bool:
        """Удалить проект; участники и документы уходят по ON DELETE CASCADE."""
        with self._lock:
            conn = self._connection()
            for table in (
                "office_redmine_creates",
                "office_redmine_issues",
                "office_redmine_mirrors",
            ):
                try:
                    conn.execute(f"DELETE FROM {table} WHERE project_id = ?", (project_id,))
                except sqlite3.OperationalError:
                    pass
            cur = conn.execute("DELETE FROM office_projects WHERE id = ?", (project_id,))
            conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Привязка мессенджера (architecture/11 §6.2, architecture/47)
    # ------------------------------------------------------------------

    def start_channel_binding(
        self, user_id: int, channel: str, code_hash: str, *, code_expires_at: float
    ) -> None:
        """Новый код; незавершённые попытки этой учётки гаснут."""
        now = _now()
        with self._lock:
            conn = self._connection()
            conn.execute(
                "UPDATE office_channel_bindings SET state = 'revoked', code_hash = NULL, "
                "updated_at = ? WHERE user_id = ? AND channel = ? AND state = 'pending'",
                (now, user_id, channel),
            )
            conn.execute(
                "INSERT INTO office_channel_bindings "
                "(user_id, channel, code_hash, code_expires_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, channel, code_hash, code_expires_at, now, now),
            )
            conn.commit()

    def mark_channel_binding_started(
        self,
        code_hash: str,
        channel: str,
        external_user_id: str,
        external_username: str,
        *,
        confirm_expires_at: float,
        now: float | None = None,
    ) -> bool:
        """Бот получил код. Один UPDATE гасит код: второй вызов ничего не найдёт."""
        ts = time.time() if now is None else now
        with self._lock:
            conn = self._connection()
            cur = conn.execute(
                "UPDATE office_channel_bindings SET code_hash = NULL, "
                "external_user_id = ?, external_username = ?, confirm_expires_at = ?, "
                "updated_at = ? "
                "WHERE code_hash = ? AND channel = ? AND state = 'pending' "
                "AND code_expires_at >= ?",
                (external_user_id, external_username, confirm_expires_at, _now(),
                 code_hash, channel, ts),
            )
            conn.commit()
            return cur.rowcount > 0

    def confirm_channel_binding(
        self, user_id: int, channel: str, external_user_id: str, *, now: float | None = None
    ) -> dict | None:
        """Владелец подтвердил именно этот аккаунт.

        None: подтверждать нечего, срок вышел или аккаунт подменили, пока человек
        вводил пароль: подтверждение не должно закрепить то, чего он не видел.
        """
        ts = time.time() if now is None else now
        with self._lock:
            conn = self._connection()
            try:
                cur = conn.execute(
                    "UPDATE office_channel_bindings SET state = 'active', "
                    "confirm_expires_at = NULL, updated_at = ? "
                    "WHERE user_id = ? AND channel = ? AND state = 'pending' "
                    "AND external_user_id = ? AND confirm_expires_at >= ?",
                    (_now(), user_id, channel, external_user_id, ts),
                )
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise ChannelBindingConflictError(channel) from exc
            conn.commit()
            if cur.rowcount == 0:
                return None
        return self.get_channel_binding(user_id, channel)

    def revoke_channel_binding(self, user_id: int, channel: str) -> bool:
        """Снимает привязку и незавершённую попытку. True: было что снять."""
        with self._lock:
            conn = self._connection()
            cur = conn.execute(
                "UPDATE office_channel_bindings SET state = 'revoked', code_hash = NULL, "
                "updated_at = ? WHERE user_id = ? AND channel = ? "
                "AND state IN ('pending', 'active')",
                (_now(), user_id, channel),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_channel_binding(self, user_id: int, channel: str) -> dict | None:
        """Текущая запись учётки: активная, иначе последняя незавершённая."""
        with self._lock:
            row = self._connection().execute(
                "SELECT * FROM office_channel_bindings "
                "WHERE user_id = ? AND channel = ? AND state IN ('pending', 'active') "
                "ORDER BY state = 'active' DESC, id DESC LIMIT 1",
                (user_id, channel),
            ).fetchone()
        return dict(row) if row is not None else None

    def has_active_binding(self, user_id: int, channel: str) -> bool:
        binding = self.get_channel_binding(user_id, channel)
        return binding is not None and binding["state"] == "active"

    def find_active_binding(self, channel: str, external_user_id: str) -> dict | None:
        with self._lock:
            row = self._connection().execute(
                "SELECT * FROM office_channel_bindings "
                "WHERE channel = ? AND external_user_id = ? AND state = 'active'",
                (channel, external_user_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def active_binding_names(self, channel: str) -> dict[int, str]:
        """Учётка → имя аккаунта мессенджера, для списка в админке."""
        with self._lock:
            rows = self._connection().execute(
                "SELECT user_id, external_username FROM office_channel_bindings "
                "WHERE channel = ? AND state = 'active'",
                (channel,),
            ).fetchall()
        return {int(r["user_id"]): r["external_username"] for r in rows}

    # ------------------------------------------------------------------
    # Участники
    # ------------------------------------------------------------------

    def add_member(self, project_id: int, user_id: int, role: str) -> dict:
        """Записывает участника; повторный вызов меняет роль."""
        with self._lock:
            conn = self._connection()
            conn.execute(
                "INSERT INTO office_members (project_id, user_id, role, added_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role",
                (project_id, user_id, role, _now()),
            )
            conn.commit()
        member = self.get_member(project_id, user_id)
        assert member is not None
        return member

    def get_member(self, project_id: int, user_id: int) -> dict | None:
        with self._lock:
            row = self._connection().execute(
                "SELECT * FROM office_members WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            ).fetchone()
        return dict(row) if row is not None else None

    def list_roles_for_user(self, user_id: int) -> list[str]:
        """Роли пользователя во всех проектах офиса (по одной на проект)."""
        with self._lock:
            rows = self._connection().execute(
                "SELECT role FROM office_members WHERE user_id = ? ORDER BY project_id",
                (user_id,),
            ).fetchall()
        return [str(r["role"]) for r in rows]

    def list_members(self, project_id: int) -> list[dict]:
        with self._lock:
            rows = self._connection().execute(
                "SELECT * FROM office_members WHERE project_id = ? ORDER BY added_at, user_id",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Документы и версии Markdown
    # ------------------------------------------------------------------

    def ensure_document(self, project_id: int, kind: str) -> dict:
        """Документ проекта данного вида (``brief``, ``spec``); создаёт, если нет."""
        existing = self.get_document(project_id, kind)
        if existing is not None:
            return existing
        with self._lock:
            conn = self._connection()
            conn.execute(
                "INSERT OR IGNORE INTO office_documents (project_id, kind, created_at) "
                "VALUES (?, ?, ?)",
                (project_id, kind, _now()),
            )
            conn.commit()
        document = self.get_document(project_id, kind)
        assert document is not None
        return document

    def get_document(self, project_id: int, kind: str) -> dict | None:
        with self._lock:
            row = self._connection().execute(
                "SELECT * FROM office_documents WHERE project_id = ? AND kind = ?",
                (project_id, kind),
            ).fetchone()
        return dict(row) if row is not None else None

    def add_version(
        self,
        document_id: int,
        *,
        markdown: str,
        source: str,
        status: str = "draft",
        created_by: int | None = None,
    ) -> dict:
        """Новая версия с номером на единицу больше последней; старые не меняются."""
        with self._lock:
            conn = self._connection()
            number = conn.execute(
                "SELECT COALESCE(MAX(number), 0) + 1 FROM office_document_versions "
                "WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]
            cur = conn.execute(
                "INSERT INTO office_document_versions "
                "(document_id, number, status, source, markdown, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (document_id, number, status, source, markdown, created_by, _now()),
            )
            conn.commit()
            version_id = int(cur.lastrowid)
        version = self.get_version(version_id)
        assert version is not None
        return version

    def get_version(self, version_id: int) -> dict | None:
        with self._lock:
            row = self._connection().execute(
                "SELECT * FROM office_document_versions WHERE id = ?", (version_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_versions(self, document_id: int) -> list[dict]:
        with self._lock:
            rows = self._connection().execute(
                "SELECT * FROM office_document_versions WHERE document_id = ? ORDER BY number",
                (document_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def latest_version(self, document_id: int) -> dict | None:
        with self._lock:
            row = self._connection().execute(
                "SELECT * FROM office_document_versions WHERE document_id = ? "
                "ORDER BY number DESC LIMIT 1",
                (document_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def set_version_status(self, version_id: int, status: str) -> dict | None:
        with self._lock:
            conn = self._connection()
            conn.execute(
                "UPDATE office_document_versions SET status = ? WHERE id = ?",
                (status, version_id),
            )
            conn.commit()
        return self.get_version(version_id)
