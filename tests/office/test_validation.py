"""Ручная валидация находок: импорт, переходы, журнал, файлы, выгрузка."""
from __future__ import annotations

import io
import json
import sqlite3
import stat
import zipfile
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from src.claude.session import SessionManager
from src.config.settings import WebSettings
from src.event_bus.bus import EventBus
from src.office import delivery, tenancy
from src.office.delivery import _validation_files
from src.office.delivery._scan import scan
from src.office.delivery._validation_decisions import entry_hash
from src.office.delivery._validation_lifecycle import TRANSITIONS
from src.office.storage import OfficeStore
from src.web.passwords import hash_password
from src.web.routes_office_validation import make_validation_router
from src.web.server import WebServer

_PASSWORD = "test-only-password"
_SECRET = "x" * 32
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
_PDF = b"%PDF-1.7\n" + b"0" * 32


def _finding(gid: str = "R4-001", **extra) -> dict:
    return {
        "gid": gid, "source_id": "A4-002", "doc": "ПМИ1", "category": "Шаги",
        "severity": "средняя", "summary": f"Суть {gid}", "why": "Причина",
        "verdict": "подтверждено", "verdict_reason": "Проверено", "clauses": ["ФТТ1 п. 4.1.1"],
        "scenarios": ["ПМИ1 сц. 6"], "redmine": [118443],
        "evidence": [{"doc": "ФТТ1", "block": f"{gid}-b1", "quote": "Цитата", "page": 3,
                      "img": "R4-001_1.png"}],
        "marked": [],
        "edits": [{"doc": "ПМИ1", "block": f"{gid}-r1", "col": "act", "old": "Было",
                   "new": "Стало", "comment": "Комментарий"}],
        **extra,
    }


def _package(tmp_path, *, findings=None, run_key="RUN4", extra=None, name="p.zip", manifest=None):
    path = tmp_path / name
    meta = {"schema_version": 1, "adapter": "doc_review_v1", "source_kind": "doc_review",
            "run_key": run_key, "title": "Прогон 4"}
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest or meta))
        archive.writestr("findings.json", json.dumps(
            [_finding()] if findings is None else findings, ensure_ascii=False))
        archive.writestr("img/R4-001_1.png", _PNG)
        archive.writestr("docs/FTT1.pdf", _PDF)
        for key, value in (extra or {}).items():
            archive.writestr(key, value)
    return path


@pytest.fixture
def store(tmp_path):
    office = OfficeStore(tmp_path / "db" / "sessions.db")
    yield office
    office.close()


@pytest.fixture
def run(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    result = delivery.import_package(store, project["id"], _package(tmp_path), actor_id=1)
    finding = delivery.list_findings(store, project["id"], result["run_id"])[0]
    return project["id"], result["run_id"], finding["id"]


def _decide(store, ids, action, seq=0, key=None, **extra):
    project_id, run_id, finding_id = ids
    return delivery.decide(
        store, project_id, run_id, finding_id, action=action, actor_id=7,
        actor_role="tester", expected_seq=seq, request_key=key or f"{action}-{seq}", **extra,
    )


# Импорт


def test_import_counts_and_repeat_is_idempotent(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    path = _package(tmp_path, findings=[_finding(), _finding("R4-002")])
    first = delivery.import_package(store, project["id"], path, actor_id=1)
    assert (first["findings"], first["assets"], first["duplicate"]) == (2, 2, False)
    again = delivery.import_package(store, project["id"], path, actor_id=1)
    assert again["duplicate"] is True and again["run_id"] == first["run_id"]
    assert len(delivery.list_runs(store, project["id"])) == 1


def test_rebuilt_package_with_other_timestamps_is_duplicate(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    paths = []
    for name, stamp in (("old.zip", (2020, 1, 1, 0, 0, 0)), ("new.zip", (2026, 10, 31, 12, 0, 0))):
        path = tmp_path / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for member, body in (
                ("manifest.json", json.dumps({
                    "schema_version": 1, "adapter": "doc_review_v1", "source_kind": "doc_review",
                    "run_key": "RUN4", "title": "Прогон 4"})),
                ("findings.json", json.dumps([_finding()], ensure_ascii=False)),
                ("img/R4-001_1.png", _PNG),
                ("docs/FTT1.pdf", _PDF),
            ):
                archive.writestr(zipfile.ZipInfo(member, date_time=stamp), body)
        paths.append(path)
    first = delivery.import_package(store, project["id"], paths[0], actor_id=1)
    again = delivery.import_package(store, project["id"], paths[1], actor_id=1)
    assert again["duplicate"] is True and again["run_id"] == first["run_id"]


def test_import_same_key_other_content_creates_new_version(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    first = delivery.import_package(store, project["id"], _package(tmp_path), actor_id=1)
    other = _package(tmp_path, findings=[_finding("R4-002")], name="q.zip")
    second = delivery.import_package(store, project["id"], other, actor_id=1)
    assert second["duplicate"] is False
    assert second["run_id"] != first["run_id"]
    rows = delivery.list_runs(store, project["id"])
    assert len(rows) == 2
    assert rows[0]["import_version"] == 2
    assert rows[0]["parent_run_id"] == first["run_id"]
    assert rows[1]["import_version"] == 1


def test_list_runs_registry_fields(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    manifest = {
        "schema_version": 1,
        "adapter": "doc_review_v1",
        "source_kind": "doc_review",
        "run_key": "RUN4",
        "title": "Прогон 4",
        "comparison_kind": "admin_vs_pmi",
        "documents": [{"role": "ftt", "name": "ФТТ1.pdf"}, {"role": "pmi", "name": "ПМИ1"}],
        "started_at": "2026-10-31T09:00:00+00:00",
    }
    delivery.import_package(
        store, project["id"], _package(tmp_path, manifest=manifest), actor_id=1,
    )
    row = delivery.list_runs(store, project["id"])[0]
    assert row["comparison_kind"] == "admin_vs_pmi"
    assert row["series_key"] == "RUN4"
    assert row["import_version"] == 1
    assert len(row["documents"]) == 2
    assert row["stats"]["total"] == 1
    assert "run_can_close" in row["stats"]


@pytest.mark.parametrize("name", [
    "../evil.png", "img/../../evil.png", "/etc/passwd", "img/evil.svg", "docs/a.html",
    "img/sub/a.png", "other.txt",
])
def test_import_rejects_names_outside_whitelist(store, tmp_path, name):
    project = store.create_project(name="Факт", created_by=1)
    path = _package(tmp_path, extra={name: _PNG})
    with pytest.raises(delivery.ValidationError) as exc:
        delivery.import_package(store, project["id"], path, actor_id=1)
    assert exc.value.code == "bad_package"
    assert not list(tmp_path.glob("**/evil*"))
    assert delivery.list_runs(store, project["id"]) == []


def test_import_rejects_symlink(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    path = _package(tmp_path)
    info = zipfile.ZipInfo("img/link.png")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(delivery.ValidationError, match="ссылки"):
        delivery.import_package(store, project["id"], path, actor_id=1)


def test_import_rejects_type_substitution(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    path = _package(tmp_path, extra={"img/fake.png": b"<svg onload=alert(1)>"})
    with pytest.raises(delivery.ValidationError, match="расширением"):
        delivery.import_package(store, project["id"], path, actor_id=1)
    assert delivery.list_runs(store, project["id"]) == []


def test_import_rejects_bomb(store, tmp_path, monkeypatch):
    from src.office.delivery import _validation_import as module

    monkeypatch.setattr(module, "MAX_UNPACKED_BYTES", 10)
    project = store.create_project(name="Факт", created_by=1)
    with pytest.raises(delivery.ValidationError) as exc:
        delivery.import_package(store, project["id"], _package(tmp_path), actor_id=1)
    assert exc.value.code == "too_large"


def test_import_rejects_not_zip(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    path = tmp_path / "x.zip"
    path.write_bytes(b"not a zip")
    with pytest.raises(delivery.ValidationError, match="zip"):
        delivery.import_package(store, project["id"], path, actor_id=1)


def test_import_rejects_missing_image_reference(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    item = _finding()
    item["evidence"][0]["img"] = "absent.png"
    with pytest.raises(delivery.ValidationError, match="снимка"):
        delivery.import_package(
            store, project["id"], _package(tmp_path, findings=[item]), actor_id=1
        )


def test_import_scanner_rejects_contact(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    item = _finding(summary="Написать на ivan@example.com")
    with pytest.raises(delivery.ValidationError) as exc:
        delivery.import_package(
            store, project["id"], _package(tmp_path, findings=[item]), actor_id=1
        )
    assert exc.value.code == "scan_failed" and "ivan" not in exc.value.message


# Переходы и журнал


def test_transitions_copy_contract_plus_one():
    assert TRANSITIONS["new"] == {"confirmed", "rejected", "duplicate"}
    assert TRANSITIONS["fixed"] == {"retested", "reopened"}
    assert TRANSITIONS["rejected"] == {"reopened"}
    assert TRANSITIONS["reopened"] == {"in_progress", "fixed", "rejected", "confirmed"}


def test_confirm_then_edits_applied(store, run):
    assert _decide(store, run, "confirm")["review_status"] == "confirmed"
    state = _decide(store, run, "edits_applied", seq=1, doc_ref="ПМИ1 v2")
    assert (state["review_status"], state["lifecycle"], state["decision_seq"]) == (
        "confirmed", "fixed", 3,
    )
    data = delivery.get_finding(store, *run)
    assert [h["lifecycle_to"] for h in data["history"]] == ["confirmed", "submitted", "fixed"]
    assert data["edits"][0]["state"] == "applied" and data["edits"][0]["doc_ref"] == "ПМИ1 v2"


def test_reject_needs_reason_and_code(store, run):
    with pytest.raises(delivery.ValidationError, match="причину"):
        _decide(store, run, "reject")
    with pytest.raises(delivery.ValidationError, match="причину отклонения"):
        _decide(store, run, "reject", why="Нет оснований")
    state = _decide(store, run, "reject", why="Нет оснований", reason_code="no_basis")
    assert state["lifecycle"] == "rejected"
    assert delivery.get_finding(store, *run)["edits"][0]["state"] == "rejected"


def test_clarify_needs_reason_and_keeps_lifecycle(store, run):
    with pytest.raises(delivery.ValidationError, match="причину"):
        _decide(store, run, "clarify")
    state = _decide(store, run, "clarify", why="Уточнить у аналитика")
    assert (state["review_status"], state["lifecycle"]) == ("needs_info", "new")
    assert _decide(store, run, "confirm", seq=1)["review_status"] == "confirmed"


def test_edits_applied_needs_document_version(store, run):
    _decide(store, run, "confirm")
    with pytest.raises(delivery.ValidationError, match="версию документа"):
        _decide(store, run, "edits_applied", seq=1)


def test_reopen_after_reject_and_confirm_again(store, run):
    _decide(store, run, "reject", why="Ошибка", reason_code="other")
    assert _decide(store, run, "reopen", seq=1)["lifecycle"] == "reopened"
    state = _decide(store, run, "confirm", seq=2)
    assert (state["review_status"], state["lifecycle"]) == ("confirmed", "confirmed")
    assert delivery.get_finding(store, *run)["edits"][0]["state"] == "queued"


def test_reopen_after_fix_returns_edits_to_queue(store, run):
    _decide(store, run, "confirm")
    _decide(store, run, "edits_applied", seq=1, doc_ref="v2")
    _decide(store, run, "reopen", seq=3)
    edit = delivery.get_finding(store, *run)["edits"][0]
    assert (edit["state"], edit["doc_ref"]) == ("queued", "")


@pytest.mark.parametrize("first,second", [
    ("confirm", "confirm"), ("confirm", "reopen"),
])
def test_bad_transition_is_refused(store, run, first, second):
    _decide(store, run, first)
    with pytest.raises(delivery.ValidationError) as exc:
        _decide(store, run, second, seq=1)
    assert exc.value.code == "bad_transition"


def test_cannot_apply_edits_to_new_finding(store, run):
    with pytest.raises(delivery.ValidationError) as exc:
        _decide(store, run, "edits_applied", doc_ref="v2")
    assert exc.value.code == "bad_transition"


def test_stale_seq_is_refused(store, run):
    _decide(store, run, "confirm")
    with pytest.raises(delivery.ValidationError) as exc:
        _decide(store, run, "reject", seq=0, why="Поздно", reason_code="other")
    assert exc.value.code == "stale"


def test_double_click_is_idempotent(store, run):
    first = _decide(store, run, "confirm", key="same")
    second = _decide(store, run, "confirm", key="same")
    assert first["decision_seq"] == second["decision_seq"] == 1
    assert len(delivery.get_finding(store, *run)["history"]) == 1


def test_scanner_refuses_secret_in_reason(store, run):
    with pytest.raises(delivery.ValidationError) as exc:
        _decide(store, run, "clarify", why="пароль: qwerty123456")
    assert exc.value.code == "scan_failed" and "qwerty" not in exc.value.message


def test_journal_refuses_update_and_chain_converges(store, run):
    _decide(store, run, "confirm")
    _decide(store, run, "edits_applied", seq=1, doc_ref="v2")
    conn = store._connection()
    with pytest.raises(sqlite3.IntegrityError, match="дописывается"):
        conn.execute("UPDATE office_validation_decisions SET why = 'подмена'")
    conn.rollback()
    prev = ""
    columns = ("finding_id", "run_id", "seq", "decision_key", "action", "review_from", "review_to",
               "lifecycle_from", "lifecycle_to", "reason_code", "why", "actor_id", "actor_role",
               "request_key", "at")
    for row in conn.execute("SELECT * FROM office_validation_decisions ORDER BY id"):
        assert row["prev_sha"] == prev
        assert row["entry_sha"] == entry_hash(prev, {k: row[k] for k in columns})
        prev = row["entry_sha"]


def test_project_delete_passes_and_keys_are_clean(store, run):
    _decide(store, run, "confirm")
    assert store.delete_project(run[0]) is True
    conn = store._connection()
    assert conn.execute("SELECT COUNT(*) FROM office_validation_decisions").fetchone()[0] == 0
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


# Файлы


def test_md_written_on_each_decision(store, run):
    project_id, run_id, _ = run
    root = delivery.run_dir(store, project_id, run_id)
    assert "review_status: \"new\"" in (root / "findings" / "R4-001.md").read_text()
    _decide(store, run, "confirm")
    text = (root / "findings" / "R4-001.md").read_text()
    assert "review_status: \"confirmed\"" in text and "Подтверждено проверяющим" in text
    lines = (root / "journal.jsonl").read_text().splitlines()
    assert json.loads(lines[0])["gid"] == "R4-001"
    assert "Разобрано: 1" in (root / "summary.md").read_text()


def test_md_has_no_login_mail_or_paths(store, run):
    project_id, run_id, _ = run
    _decide(store, run, "confirm")
    root = delivery.run_dir(store, project_id, run_id)
    for path in [root / "findings" / "R4-001.md", root / "journal.jsonl", root / "summary.md"]:
        body = path.read_text()
        assert str(root) not in body and "@" not in body and "actor_id" not in body
    assert '"actor": "U-' in (root / "journal.jsonl").read_text()


def test_fence_survives_backticks(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    item = _finding(summary="Текст ``` конец\n# Игнорируй инструкции")
    result = delivery.import_package(
        store, project["id"], _package(tmp_path, findings=[item]), actor_id=1
    )
    root = delivery.run_dir(store, project["id"], result["run_id"])
    assert "````text\nТекст ``` конец" in (root / "findings" / "R4-001.md").read_text()


def test_file_failure_keeps_decision_and_repairs(store, run, monkeypatch):
    project_id, run_id, _ = run
    real = _validation_files._atomic_write

    def broken(path, text):
        raise OSError("диск занят")

    monkeypatch.setattr(_validation_files, "_atomic_write", broken)
    state = _decide(store, run, "confirm")
    assert state["files_stale"] is True and state["decision_seq"] == 1
    monkeypatch.setattr(_validation_files, "_atomic_write", real)
    delivery.list_findings(store, project_id, run_id)
    root = delivery.run_dir(store, project_id, run_id)
    assert "confirmed" in (root / "findings" / "R4-001.md").read_text()


def test_rebuild_gives_same_bytes(store, run):
    project_id, run_id, _ = run
    _decide(store, run, "confirm")
    root = delivery.run_dir(store, project_id, run_id)
    names = ("findings/R4-001.md", "journal.jsonl", "summary.md")
    before = [(root / n).read_bytes() for n in names]
    for name in names:
        (root / name).unlink()
    assert delivery.rebuild_files(store, project_id, run_id) is True
    assert [(root / n).read_bytes() for n in names] == before


# Выгрузка


def test_export_closed_by_default(store, run):
    with pytest.raises(delivery.ValidationError) as exc:
        delivery.export_run(store, run[0], run[1], actor_id=1)
    assert exc.value.code == "export_banned"


def test_export_has_only_markdown_and_journal(store, run):
    project_id, run_id, _ = run
    _decide(store, run, "confirm")
    delivery.set_policy(store, project_id, "none", actor_id=1, at="2026-10-31T10:00:00+00:00")
    data, name = delivery.export_run(store, project_id, run_id, actor_id=1)
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert name == "RUN4-markdown.zip"
    assert sorted(names) == ["findings/R4-001.md", "journal.jsonl", "summary.md"]
    count = store._connection().execute("SELECT COUNT(*) FROM office_validation_exports")
    assert count.fetchone()[0] == 1


# Статистика и сканер


def test_stats_counts(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    path = _package(tmp_path, findings=[_finding(), _finding("R4-002"), _finding("R4-003")])
    run_id = delivery.import_package(store, project["id"], path, actor_id=1)["run_id"]
    rows = delivery.list_findings(store, project["id"], run_id)
    _decide(store, (project["id"], run_id, rows[0]["id"]), "confirm")
    _decide(store, (project["id"], run_id, rows[0]["id"]), "edits_applied", seq=1, doc_ref="v2")
    _decide(store, (project["id"], run_id, rows[1]["id"]), "reject", why="Нет", reason_code="other")
    stats = delivery.get_run(store, project["id"], run_id)["stats"]
    assert (stats["total"], stats["reviewed"], stats["findings_edits_done"]) == (3, 2, 1)
    assert stats["run_can_close"] is False
    assert stats["pending_decision"] == 1
    assert (stats["edits_total"], stats["edits_applied"]) == (3, 1)
    assert stats["llm_agreement"] == 0.5


@pytest.mark.parametrize("text,kind", [
    ("mail ivan@example.com", "email"), ("тел +7 (912) 345-67-89", "phone"),
    ("sk-ant-api03-abcdefghijklmnop", "api_key"), ("token=abcdef123456", "assignment"),
    ("Иванов Иван Иванович", "fio"), ("Иванов И.И.", "fio_short"),
])
def test_scanner_hits(text, kind):
    assert kind in scan(text)


@pytest.mark.parametrize("text", [
    "Совершить клик по аватару / ФИО / должности пользователя",
    "ФТТ1 п. 4.1.1 и 4.1.3: открытие в текущей вкладке",
    "Организационная структура Руководитель сотрудников",
])
def test_scanner_passes_plain_text(text):
    assert scan(text) == []


def test_traceability_defect_class_on_import(store, tmp_path):
    project = store.create_project(name="Факт", created_by=1)
    finding = _finding(summary="В ПМИ нет проверки требования REQ-0042")
    path = _package(tmp_path, findings=[finding])
    run_id = delivery.import_package(store, project["id"], path, actor_id=1)["run_id"]
    row = store._connection().execute(
        "SELECT defect_class FROM office_validation_findings WHERE run_id = ?", (run_id,)
    ).fetchone()
    assert row["defect_class"] == "traceability_break"


def test_redmine_export_rejects_unconfirmed(store, run):
    project_id, run_id, finding_id = run
    token = "user-token-1234567890"
    with pytest.raises(delivery.ValidationError) as exc:
        delivery.export_finding_to_redmine(
            store, project_id, run_id, finding_id, api_key=token, request_key="rk1",
        )
    assert exc.value.code == "bad_transition"


def _stand_package(tmp_path, *, findings, run_key="STAND-01"):
    manifest = {
        "schema_version": 1,
        "adapter": "stand_run_v1",
        "source_kind": "stand_run",
        "run_key": run_key,
        "title": "Соответствие стенда",
        "stand_version": "tatnet-demo",
    }
    return _package(tmp_path, findings=findings, run_key=run_key, manifest=manifest)


def test_stand_defect_class_on_stand_run_import(store, tmp_path):
    """Сценарий stand_compliance: большинство находок без явного класса → stand_defect."""
    project = store.create_project(name="Факт", created_by=1)
    findings = [
        _finding("S-001", summary="Кнопка «Сохранить» не активна на шаге 3"),
        _finding("S-002", summary="API возвращает 500 на сценарии оплаты"),
        _finding("S-003", summary="Поле ИНН не маскируется"),
        _finding("S-004", summary="Таймаут загрузки вложений"),
        _finding("S-005", defect_class="document_defect", summary="Опечатка в тексте ПМИ"),
    ]
    path = _stand_package(tmp_path, findings=findings)
    run_id = delivery.import_package(store, project["id"], path, actor_id=1)["run_id"]
    rows = store._connection().execute(
        "SELECT defect_class FROM office_validation_findings WHERE run_id = ? ORDER BY gid",
        (run_id,),
    ).fetchall()
    assert [r["defect_class"] for r in rows] == [
        "stand_defect", "stand_defect", "stand_defect", "stand_defect", "document_defect",
    ]


def test_stand_remediation_aggregate_redmine(store, tmp_path, monkeypatch):
    from src.office import redmine_mirror

    project = store.create_project(name="Факт", created_by=1)
    findings = [_finding(f"S-{i:03d}", summary=f"Дефект стенда {i}") for i in range(1, 4)]
    path = _stand_package(tmp_path, findings=findings)
    run_id = delivery.import_package(store, project["id"], path, actor_id=1)["run_id"]
    rows = delivery.list_findings(store, project["id"], run_id)
    for row in rows:
        _decide(store, (project["id"], run_id, row["id"]), "confirm")
    stats = delivery.get_run(store, project["id"], run_id)["stats"]
    assert stats["stand_remediation_ready"] is True

    cipher = redmine_mirror.cipher_for("secret")
    redmine_mirror.save_account(
        store, cipher, base_url="https://127.0.0.1", redmine_project="fact",
        api_key="platform-key-1234567890",
    )
    captured = {}

    class _Client:
        def _call(self, *_args, **_kwargs):
            return {"user": {"id": 7}}

        def create_issue(self, _project, fields):
            captured["fields"] = fields
            return {"issue": {"id": 777}}

    monkeypatch.setattr(
        "src.office.delivery._validation_redmine.HttpRedmine",
        lambda _base, _token: _Client(),
    )
    out = delivery.export_run_stand_remediation(
        store, project["id"], run_id, api_key="user-token-1234567890", request_key="ignored",
    )
    assert out["issue_id"] == 777
    assert out["findings"] == 3
    assert "Исправление стенда по прогону STAND-01" in captured["fields"]["subject"]
    assert "S-001" in captured["fields"]["description"]
    detail = delivery.get_run(store, project["id"], run_id)
    assert detail["stand_remediation_issue_id"] == 777


def test_redmine_export_creates_issue(store, run, monkeypatch):
    from src.office import redmine_mirror

    project_id, run_id, finding_id = run
    _decide(store, run, "confirm")
    cipher = redmine_mirror.cipher_for("secret")
    redmine_mirror.save_account(
        store,
        cipher,
        base_url="https://127.0.0.1",
        redmine_project="fact",
        api_key="platform-key-1234567890",
    )

    class _Client:
        def _call(self, *_args, **_kwargs):
            return {"user": {"id": 7}}

        def create_issue(self, _project, _fields):
            return {"issue": {"id": 901}}

    monkeypatch.setattr(
        "src.office.delivery._validation_redmine.HttpRedmine",
        lambda _base, _token: _Client(),
    )
    token = "user-token-1234567890"
    out = delivery.export_finding_to_redmine(
        store, project_id, run_id, finding_id, api_key=token, request_key="rk-export-1",
    )
    assert out["issue_id"] == 901
    assert out["created"] is True
    card = delivery.get_finding(store, project_id, run_id, finding_id)
    assert "901" in str(card["redmine_links"][0])


# HTTP: права


@pytest.fixture
def server(tmp_path):
    sm = SessionManager(storage_path=tmp_path / "sessions.db")
    settings = WebSettings(
        enabled=True, host="127.0.0.1", port=0, jwt_secret=_SECRET, telegram_bot_username="t"
    )
    srv = WebServer(
        settings=settings, allowed_user_ids=[], bot_username="t", session_manager=sm,
        event_bus=EventBus(), jwt_secret=_SECRET,
    )
    try:
        yield srv, sm
    finally:
        srv.office_store.close()
        sm.close_sync()
        sm._engine.sync_engine.dispose()


@asynccontextmanager
async def _client(srv: WebServer, username: str):
    async with AsyncClient(transport=ASGITransport(app=srv.app), base_url="http://test") as client:
        r = await client.post("/api/auth/login", json={"username": username, "password": _PASSWORD})
        assert r.status_code == 200
        yield client


def _user(sm, name, *, is_admin=False) -> int:
    return sm.create_local_user(
        username=name, password_hash=hash_password(_PASSWORD), is_admin=is_admin
    )


def _setup(srv, sm, tmp_path) -> dict:
    office = srv.office_store
    lead = _user(sm, "lead")
    project = office.create_project(name="Факт", created_by=lead)
    pid = project["id"]
    tenancy.record_creator(office, pid, lead)
    roles = {
        "tester": "tester", "analyst": "business_analyst", "system": "system_analyst",
        "dev": "developer", "observer": "observer", "pmo": "pmo_head", "arch": "architect",
        "client": "customer_representative", "signer": "customer_signatory",
    }
    for name, role in roles.items():
        office.add_member(pid, _user(sm, name), role)
    other = _user(sm, "other")
    other_project = office.create_project(name="Чужой", created_by=other)
    tenancy.record_creator(office, other_project["id"], other)
    _user(sm, "root", is_admin=True)
    run = delivery.import_package(office, pid, _package(tmp_path), actor_id=lead)
    rows = delivery.list_findings(office, pid, run["run_id"])
    assets = delivery.get_run(office, pid, run["run_id"])["docs"]
    return {"pid": pid, "rid": run["run_id"], "fid": rows[0]["id"], "aid": assets[0]["id"]}


def _body(action="clarify", key="k1", seq=0) -> dict:
    return {"action": action, "expected_seq": seq, "request_key": key, "why": "Уточнить"}


async def test_every_route_closed_for_customer(server, tmp_path):
    srv, sm = server
    ids = _setup(srv, sm, tmp_path)
    router = make_validation_router(
        office_store=srv.office_store, require_project=lambda: None, session_manager=sm
    )
    assert len(router.routes) >= 9
    async with _client(srv, "client") as client:
        for route in router.routes:
            path = route.path.format(
                project_id=ids["pid"], run_id=ids["rid"], finding_id=ids["fid"],
                asset_id=ids["aid"],
            )
            for method in route.methods:
                response = await client.request(
                    method, f"/api/office{path}",
                    json=_body() if method in ("POST", "PUT") else None,
                )
                assert response.status_code == 403, (method, path, response.status_code)


@pytest.mark.parametrize("user,expected", [
    ("lead", 200), ("tester", 200), ("analyst", 200), ("system", 200),
    ("dev", 403), ("observer", 403), ("pmo", 403), ("arch", 403), ("root", 403),
    ("client", 403), ("signer", 403), ("other", 404),
])
async def test_who_can_decide(server, tmp_path, user, expected):
    srv, sm = server
    ids = _setup(srv, sm, tmp_path)
    url = (f"/api/office/projects/{ids['pid']}/validation/runs/{ids['rid']}"
           f"/findings/{ids['fid']}/decisions")
    async with _client(srv, user) as client:
        response = await client.post(url, json=_body())
    assert response.status_code == expected, response.text


@pytest.mark.parametrize("user,expected", [
    ("lead", 200), ("root", 200), ("tester", 403), ("dev", 403), ("client", 403), ("other", 404),
])
async def test_who_can_set_policy(server, tmp_path, user, expected):
    srv, sm = server
    ids = _setup(srv, sm, tmp_path)
    async with _client(srv, user) as client:
        response = await client.put(
            f"/api/office/projects/{ids['pid']}/validation/policy", json={"export_ban": "none"},
        )
    assert response.status_code == expected


async def test_foreign_project_sees_nothing(server, tmp_path):
    srv, sm = server
    ids = _setup(srv, sm, tmp_path)
    base = f"/api/office/projects/{ids['pid']}/validation"
    async with _client(srv, "other") as client:
        for path in ("/runs", f"/runs/{ids['rid']}", f"/runs/{ids['rid']}/assets/{ids['aid']}"):
            assert (await client.get(base + path)).status_code == 404


async def test_asset_of_other_run_is_not_served(server, tmp_path):
    srv, sm = server
    ids = _setup(srv, sm, tmp_path)
    office = srv.office_store
    other_project = office.create_project(name="Ещё", created_by=1)
    second = delivery.import_package(
        office, other_project["id"], _package(tmp_path, name="s.zip"), actor_id=1
    )
    foreign = delivery.get_run(office, other_project["id"], second["run_id"])["docs"][0]["id"]
    base = f"/api/office/projects/{ids['pid']}/validation/runs/{ids['rid']}"
    async with _client(srv, "lead") as client:
        ok = await client.get(f"{base}/assets/{ids['aid']}")
        assert ok.status_code == 200 and ok.headers["content-type"] == "application/pdf"
        assert ok.headers["x-content-type-options"] == "nosniff"
        assert ok.headers["content-disposition"].startswith("inline")
        assert (await client.get(f"{base}/assets/{foreign}")).status_code == 404


async def test_import_over_http_only_for_manager(server, tmp_path):
    srv, sm = server
    ids = _setup(srv, sm, tmp_path)
    data = _package(tmp_path, run_key="RUN5", name="five.zip").read_bytes()
    url = f"/api/office/projects/{ids['pid']}/validation/runs/import"
    async with _client(srv, "tester") as client:
        assert (await client.post(url, content=data)).status_code == 403
    async with _client(srv, "lead") as client:
        response = await client.post(url, content=data)
    assert response.status_code == 201, response.text
    assert response.json()["findings"] == 1
    assert not list((delivery.data_root(srv.office_store) / ".incoming").glob("*"))


async def test_full_decision_flow_over_http(server, tmp_path):
    srv, sm = server
    ids = _setup(srv, sm, tmp_path)
    base = f"/api/office/projects/{ids['pid']}/validation/runs/{ids['rid']}"
    async with _client(srv, "tester") as client:
        confirm = await client.post(
            f"{base}/findings/{ids['fid']}/decisions", json=_body("confirm"),
        )
        assert confirm.status_code == 200, confirm.text
        stale = await client.post(
            f"{base}/findings/{ids['fid']}/decisions", json=_body("clarify", "k2", 0),
        )
        assert stale.status_code == 409
        empty = await client.post(
            f"{base}/findings/{ids['fid']}/decisions",
            json={**_body("clarify", "k3", 1), "why": ""},
        )
        assert empty.status_code == 422
        card = (await client.get(f"{base}/findings/{ids['fid']}")).json()
        assert card["history"][0]["actor"] == "tester" and "actor_id" not in card["history"][0]
        assert (await client.get(base)).json()["stats"]["validated"] == 1


async def test_delete_project_with_runs_only_for_manager(server, tmp_path):
    srv, sm = server
    ids = _setup(srv, sm, tmp_path)
    folder = delivery.run_dir(srv.office_store, ids["pid"], ids["rid"])
    url = f"/api/office/projects/{ids['pid']}"
    assert folder.is_dir()
    async with _client(srv, "dev") as client:
        assert (await client.delete(url)).status_code == 403
    async with _client(srv, "lead") as client:
        assert (await client.delete(url)).status_code == 204
    assert not folder.exists()
