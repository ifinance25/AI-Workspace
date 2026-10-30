#!/usr/bin/env python3
"""Записать справочники формы Redmine (kanban) в SQLite из data/fixtures/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.claude.session import SessionManager
from src.office.redmine_mirror._lookups import default_fixture_path, seed_lookups
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
    parser = argparse.ArgumentParser(description="Сид справочников Redmine в SQLite")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="путь к sessions.db (иначе SESSION_DATABASE_PATH из .env)",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="JSON фикстура (по умолчанию data/fixtures/redmine_kanban_lookups.json)",
    )
    args = parser.parse_args()
    db_path = args.db or _load_env_db()
    if not db_path.is_file():
        print(f"База не найдена: {db_path}", file=sys.stderr)
        return 1

    sm = SessionManager(storage_path=db_path)
    store = OfficeStore(sm.storage_path)
    fixture = args.fixture or default_fixture_path()
    payload = seed_lookups(store, fixture_path=fixture)
    filters = payload.get("filters") or {}
    print(
        f"Справочники Redmine записаны в {db_path}: "
        f"типов={len(filters.get('types', []))}, "
        f"статусов={len(filters.get('statuses', []))}, "
        f"исполнителей={len(filters.get('assignees', []))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
