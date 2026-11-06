// Подписи статусов, причин и правила доступных действий. Сервер остаётся
// источником правды: недопустимое действие он отклоняет с 409.
import type { DecisionAction, FindingRow, ReviewStatus } from "@/components/runs/runsApi";

export const STATUS_LABEL: Record<ReviewStatus, string> = {
  new: "Не разобрано",
  confirmed: "Подтверждено",
  rejected: "Отклонено",
  needs_info: "На уточнение",
};

export const FIXED_LABEL = "Правки внесены";

export const REASONS: Array<{ code: string; label: string }> = [
  { code: "wrong_fact", label: "Неверный факт" },
  { code: "no_basis", label: "Нет основания в документе" },
  { code: "contradicts_customer", label: "Противоречит заказчику" },
  { code: "contradicts_decision", label: "Противоречит принятому решению" },
  { code: "out_of_scope", label: "Вне объёма" },
  { code: "outdated_input", label: "Входные данные устарели" },
  { code: "unclear", label: "Неясно" },
  { code: "style", label: "Только стиль" },
  { code: "other", label: "Другое" },
];

export const ACTION_LABEL: Record<DecisionAction, string> = {
  confirm: "Подтверждено",
  reject: "Отклонено",
  clarify: "На уточнение",
  edits_applied: "Правки внесены",
  reopen: "Вернуть в разбор",
};

export const LIFECYCLE_LABEL: Record<string, string> = {
  new: "новая",
  confirmed: "подтверждена",
  submitted: "правки переданы",
  in_progress: "в работе",
  fixed: "правки внесены",
  retested: "перепроверена",
  closed: "закрыта",
  reopened: "возвращена в разбор",
  rejected: "отклонена",
  duplicate: "дубликат",
};

export const EDIT_STATE_LABEL: Record<string, string> = {
  proposed: "предложена",
  queued: "в очереди",
  applied: "внесена",
  rejected: "отклонена",
};

export const ROLE_LABEL: Record<string, string> = {
  project_manager: "менеджер проекта",
  pmo_head: "руководитель проектного офиса",
  observer: "наблюдатель",
  business_analyst: "бизнес-аналитик",
  system_analyst: "системный аналитик",
  architect: "архитектор",
  developer: "разработчик",
  tester: "тестировщик",
  customer_representative: "представитель заказчика",
  customer_signatory: "подписант заказчика",
  system_admin: "администратор системы",
};

export type StatusFilter = "all" | ReviewStatus | "fixed" | "undecided" | "traceability" | "stand_defect";

export function displayStatus(f: Pick<FindingRow, "review_status" | "lifecycle">): string {
  return f.lifecycle === "fixed" ? FIXED_LABEL : STATUS_LABEL[f.review_status];
}

export function statusTone(f: Pick<FindingRow, "review_status" | "lifecycle">): string {
  if (f.lifecycle === "fixed") {
    return "bg-[var(--status-success-fg)] text-[var(--bg-canvas)]";
  }
  if (f.review_status === "confirmed") {
    return "bg-[var(--status-success-bg)] text-[var(--status-success-fg)]";
  }
  if (f.review_status === "rejected") {
    return "bg-[var(--status-error-bg)] text-[var(--status-error-fg)]";
  }
  if (f.review_status === "needs_info") {
    return "bg-[color-mix(in_srgb,var(--accent-brand)_18%,transparent)] text-[var(--fg-primary)]";
  }
  return "bg-[var(--bg-hover)] text-[var(--fg-secondary)]";
}

export function matchesFilter(f: FindingRow, filter: StatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "undecided") {
    return (f.review_status === "new" || f.review_status === "needs_info") && f.lifecycle !== "fixed";
  }
  if (filter === "traceability") return f.defect_class === "traceability_break";
  if (filter === "stand_defect") return f.defect_class === "stand_defect";
  if (filter === "fixed") return f.lifecycle === "fixed";
  return f.review_status === filter && f.lifecycle !== "fixed";
}

export function availableActions(
  f: Pick<FindingRow, "review_status" | "lifecycle">,
): DecisionAction[] {
  const open = f.review_status === "new" || f.review_status === "needs_info";
  const out: DecisionAction[] = [];
  if (open) out.push("confirm");
  if (
    (open || f.review_status === "confirmed") &&
    f.lifecycle !== "submitted" &&
    f.lifecycle !== "fixed"
  ) {
    out.push("reject");
  }
  if ((open || f.review_status === "confirmed") && f.lifecycle !== "fixed") out.push("clarify");
  if (f.review_status === "confirmed" && f.lifecycle === "confirmed") out.push("edits_applied");
  if (f.lifecycle === "rejected" || f.lifecycle === "fixed") out.push("reopen");
  return out;
}

export function formatStamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("ru-RU", { timeZone: "Europe/Moscow" });
}

/** Нормализация для сравнения подписей в истории (без точки в конце, нижний регистр). */
export function historyCompareNorm(s: string): string {
  return s.replace(/\.$/, "").trim().toLowerCase();
}

const REOPEN_HINT = /вернут|возврат|разбор/;

/**
 * Два фрагмента текста не должны идти подряд, если повторяют смысл
 * (одинаково, вложенность, общие значимые слова или явный сценарий «в разбор»).
 */
export function historyPhrasesRedundant(a: string, b: string): boolean {
  const na = historyCompareNorm(a);
  const nb = historyCompareNorm(b);
  if (!na || !nb) return false;
  if (na === nb) return true;
  if (na.length >= 4 && nb.length >= 4 && (na.includes(nb) || nb.includes(na))) return true;
  const wa = na.split(/\s+/).filter((w) => w.length > 2);
  const wb = nb.split(/\s+/).filter((w) => w.length > 2);
  if (wa.length && wb.length) {
    const setB = new Set(wb);
    let inter = 0;
    for (const w of wa) if (setB.has(w)) inter++;
    const union = new Set([...wa, ...wb]).size;
    if (union > 0 && inter / union >= 0.45) return true;
  }
  if (REOPEN_HINT.test(na) && REOPEN_HINT.test(nb)) return true;
  return false;
}

/** Подпись класса дефекта для фильтра и опций (не дублирует статус). */
export function defectClassFilterLabel(code: string): string {
  switch (code) {
    case "traceability_break":
      return "Разрыв прослеживаемости";
    case "stand_defect":
      return "Дефект стенда";
    case "document_defect":
      return "Дефект в документе";
    default:
      return code;
  }
}
