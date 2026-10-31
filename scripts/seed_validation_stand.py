#!/usr/bin/env python3
"""Наполнить тестовый стенд валидации: учётки по ролям, проект, пакет прогона, решения.

Запускать из каталога стенда, чтобы не подхватить ``.env`` с настоящими секретами:
``run_validation_stand.sh`` так и делает. Пароли случайные, пишутся в файл учёток
с правами 0600 и в вывод не попадают.
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.claude.session import SessionManager  # noqa: E402
from src.office import delivery, tenancy  # noqa: E402
from src.office.storage import OfficeStore  # noqa: E402
from src.web.passwords import hash_password  # noqa: E402

# логин, роль в проекте (None: нет членства), администратор, подпись
ACCOUNTS = [
    ("admin", None, True, "администратор системы, не участник проекта"),
    ("lead", "project_manager", False, "менеджер проекта: решает, загружает, выгружает"),
    ("tester", "tester", False, "тестировщик: решает"),
    ("analyst", "business_analyst", False, "бизнес-аналитик: решает"),
    ("sysanalyst", "system_analyst", False, "системный аналитик: решает"),
    ("developer", "developer", False, "разработчик: только смотрит"),
    ("observer", "observer", False, "наблюдатель: только смотрит"),
    ("customer", "customer_representative", False, "представитель заказчика: раздел закрыт"),
    ("other", "project_manager", False, "менеджер чужого проекта: этот проект не видит"),
]
DEMO = [
    ("R4-001", [("confirm", {}), ("edits_applied", {"doc_ref": "ПМИ1 от 02.11.2026"})]),
    ("R4-002", [("reject", {"reason_code": "no_basis", "why": "Требования нет в ФТТ"})]),
    ("R4-003", [("clarify", {"why": "Уточнить у аналитика"})]),
    ("R4-004", [("confirm", {})]),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--package", type=Path, default=None)
    parser.add_argument("--accounts-file", required=True, type=Path)
    args = parser.parse_args()

    args.data_dir.mkdir(parents=True, exist_ok=True)
    db = args.data_dir / "sessions.db"
    manager = SessionManager(storage_path=db)
    office = OfficeStore(db)
    lines = ["# Учётки тестового стенда валидации. Не коммитить, не пересылать.", ""]
    ids: dict[str, int] = {}
    try:
        for login, _role, is_admin, note in ACCOUNTS:
            password = secrets.token_hex(8)
            ids[login] = manager.create_local_user(
                username=login, password_hash=hash_password(password), is_admin=is_admin
            )
            lines.append(f"{login} / {password}    {note}")
        project = office.create_project(name="ФАКТ: валидация прогона № 4", created_by=ids["lead"])
        tenancy.record_creator(office, project["id"], ids["lead"])
        for login, role, _admin, _note in ACCOUNTS:
            if role and login not in ("lead", "other"):
                office.add_member(project["id"], ids[login], role)
        foreign = office.create_project(name="Чужой проект", created_by=ids["other"])
        tenancy.record_creator(office, foreign["id"], ids["other"])

        if args.package and args.package.is_file():
            result = delivery.import_package(
                office, project["id"], args.package, actor_id=ids["lead"]
            )
            rows = {r["gid"]: r for r in delivery.list_findings(
                office, project["id"], result["run_id"])}
            for gid, steps in DEMO:
                seq = 0
                for number, (action, extra) in enumerate(steps):
                    state = delivery.decide(
                        office, project["id"], result["run_id"], rows[gid]["id"], action=action,
                        actor_id=ids["tester"], actor_role="tester", expected_seq=seq,
                        request_key=f"seed-{gid}-{number}", **extra,
                    )
                    seq = state["decision_seq"]
            print(f"Прогон загружен: находок {result['findings']}, решений заложено {len(DEMO)}")
        else:
            print("Пакет прогона не найден: проект создан пустым", file=sys.stderr)
        lines += ["", f"Проект стенда: id {project['id']}, чужой проект: id {foreign['id']}"]
    finally:
        office.close()
        manager.close_sync()
        manager._engine.sync_engine.dispose()
    args.accounts_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.accounts_file.chmod(0o600)
    return 0


if __name__ == "__main__":
    sys.exit(main())
