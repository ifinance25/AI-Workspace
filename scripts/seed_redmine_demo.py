#!/usr/bin/env python3
"""Заполнить зеркало Redmine демо-задачами для просмотра Kanban на локальном стенде."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.claude.session import SessionManager
from src.office import redmine_mirror
from src.office.storage import OfficeStore


def _load_env_db() -> Path:
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == "SESSION_DATABASE_PATH":
                raw = val.strip().strip('"').strip("'")
                if raw:
                    p = Path(raw)
                    return p if p.is_absolute() else ROOT / p
    return ROOT / "data" / "sessions.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="Сид демо-задач Redmine в SQLite зеркало")
    parser.add_argument(
        "--project-id",
        type=int,
        default=1,
        help="id проекта офиса (office_projects.id)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="путь к sessions.db (иначе SESSION_DATABASE_PATH из .env)",
    )
    args = parser.parse_args()
    db_path = args.db or _load_env_db()
    if not db_path.is_file():
        print(f"База не найдена: {db_path}", file=sys.stderr)
        return 1

    sm = SessionManager(storage_path=db_path)
    store = OfficeStore(sm.storage_path)
    project = store.get_project(args.project_id)
    if project is None:
        print(f"Проект офиса id={args.project_id} не найден в {db_path}", file=sys.stderr)
        return 1

    count = redmine_mirror.seed_demo_mirror(store, args.project_id)
    print(f"Записано {count} демо-задач для проекта «{project['name']}» (id={args.project_id}).")
    print(f"Откройте: /office/{args.project_id}/redmine → вкладка «Доска».")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
