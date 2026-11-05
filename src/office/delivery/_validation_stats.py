"""Статистика прогона. Позже считать её будет модуль ``insight``."""
from __future__ import annotations

from typing import Any

_SLICES = {"severity": "severity_raw", "doc": "doc", "category": "category"}


def run_stats(conn: Any, run_id: int) -> dict:
    """Цифры дашборда по одному прогону."""
    by_status = {r["review_status"]: r["n"] for r in conn.execute(
        "SELECT review_status, COUNT(*) AS n FROM office_validation_findings "
        "WHERE run_id = ? GROUP BY review_status", (run_id,))}
    edits = conn.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(e.state = 'applied'), 0) AS applied "
        "FROM office_validation_edits e JOIN office_validation_findings f ON f.id = e.finding_id "
        "WHERE f.run_id = ?", (run_id,)).fetchone()
    done = conn.execute(
        "SELECT COUNT(*) FROM office_validation_findings f WHERE f.run_id = ? "
        "AND f.lifecycle = 'fixed'", (run_id,)).fetchone()[0]
    confirmed, rejected = by_status.get("confirmed", 0), by_status.get("rejected", 0)
    pending_new = by_status.get("new", 0)
    pending_info = by_status.get("needs_info", 0)
    reviewed = confirmed + rejected
    stats = {
        "total": sum(by_status.values()),
        "by_status": by_status,
        # «Разобрано»: только подтверждено и отклонено, без «на уточнении».
        "reviewed": reviewed,
        "validated": reviewed,
        "pending_decision": pending_new + pending_info,
        "run_can_close": pending_new == 0 and pending_info == 0,
        "findings_edits_done": done,
        "edits_total": edits["total"],
        "edits_applied": edits["applied"],
        # Скептик оставил все находки, значит совпадение это доля подтверждённых людьми.
        "llm_agreement": round(confirmed / reviewed, 3) if reviewed else None,
        "slices": {},
    }
    for name, column in _SLICES.items():
        stats["slices"][name] = [dict(r) for r in conn.execute(
            f"SELECT {column} AS label, COUNT(*) AS total, "
            "SUM(review_status IN ('confirmed', 'rejected')) AS validated, "
            "SUM(lifecycle = 'fixed') AS fixed "
            "FROM office_validation_findings WHERE run_id = ? "
            f"GROUP BY {column} ORDER BY total DESC, label", (run_id,))]
    return stats
