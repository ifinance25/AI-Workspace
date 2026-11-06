"""Сборка payload Redmine для находки (шаблон v6)."""
from __future__ import annotations

from src.office.delivery._validation_redmine_builder import (
    REDMINE_TICKET_TEMPLATE_PATH,
    REDMINE_TICKET_TEMPLATE_VERSION,
    build_description,
    build_issue_fields,
    build_subject,
    related_issue_ids,
)


def _finding(**extra):
    base = {
        "gid": "R4-001",
        "source_id": "A4-002",
        "doc": "ПМИ1",
        "category": "Шаги",
        "defect_class": "document_defect",
        "severity_raw": "significant",
        "summary": "Неверный текст кнопки",
        "why": "Расхождение с ФТТ",
        "clauses": ["ФТТ1 п. 4.1.1"],
        "scenarios": ["ПМИ1 сц. 6"],
        "section": "Спасибо: благодарности",
        "redmine": [118443],
        "evidence": [{"doc": "ФТТ1", "quote": "Цитата", "page": 3, "img": "R4-001_1.png"}],
        "history": [{"review_to": "confirmed", "at": "2026-10-21T12:00:00+00:00"}],
    }
    base.update(extra)
    return base


def test_template_file_present():
    assert REDMINE_TICKET_TEMPLATE_VERSION == 6
    assert REDMINE_TICKET_TEMPLATE_PATH.is_file()


def test_subject_uses_ftt_section_prefix():
    subject = build_subject(_finding())
    assert subject.startswith("Спасибо:")
    assert "Неверный текст" in subject
    assert "[R4-001]" not in subject


def test_description_section_order_and_textile():
    text = build_description(_finding(), run_key="RUN4", attachment_names=["R4-001_1.png"])
    pos_pre = text.index("*Предусловия:*")
    pos_steps = text.index("*Шаги воспроизведения:*")
    pos_req = text.index("*Требование:*")
    pos_crit = text.index("*Критерии приёмки:*")
    pos_src = text.index("*Источник:*")
    assert pos_pre < pos_steps < pos_req < pos_crit < pos_src
    assert "table{background:#ffffff}." in text
    assert "|_. Шаг |_. Действие |_" in text
    assert "{background:#fdecec}." in text
    assert "{{collapse(скриншот) !R4-001_1.png! }}" in text
    assert "Сравниваемая область обведена красной рамкой." in text
    assert text.index("---") < pos_src
    assert "прогон RUN4" in text
    assert "Связанные задачи" not in text


def test_issue_fields_custom_fields():
    fields = build_issue_fields(_finding(), run_key="RUN4")
    assert fields["tracker_id"] == 1
    assert fields["status_id"] == 1
    assert fields["priority_id"] == 2
    cf = {item["id"]: item["value"] for item in fields["custom_fields"]}
    assert cf[4] == "Документ"
    assert cf[7] == ["dev"]
    assert cf[25] == ["Десктоп"]
    assert cf[15] == ""


def test_related_issue_ids():
    assert related_issue_ids(_finding()) == [118443]
