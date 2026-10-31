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

export type StatusFilter = "all" | ReviewStatus | "fixed";

export function displayStatus(f: Pick<FindingRow, "review_status" | "lifecycle">): string {
  return f.lifecycle === "fixed" ? FIXED_LABEL : STATUS_LABEL[f.review_status];
}

export function statusTone(f: Pick<FindingRow, "review_status" | "lifecycle">): string {
  if (f.lifecycle === "fixed") return "bg-emerald-700/40 text-emerald-200";
  if (f.review_status === "confirmed") return "bg-emerald-900/40 text-emerald-300";
  if (f.review_status === "rejected") return "bg-red-900/40 text-red-300";
  if (f.review_status === "needs_info") return "bg-amber-900/40 text-amber-300";
  return "bg-[var(--bg-hover)] text-[var(--fg-secondary)]";
}

export function matchesFilter(f: FindingRow, filter: StatusFilter): boolean {
  if (filter === "all") return true;
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
