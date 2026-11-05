import type { ComparisonKind } from "@/components/runs/runsApi";

const LABELS: Record<ComparisonKind, string> = {
  ftt_vs_stand: "ФТТ ↔ стенд (соответствие стенда)",
  spmi_vs_ftt: "ПМИ ↔ ФТТ",
  admin_vs_pmi: "Руководство администратора ↔ ПМИ",
  pmi_vs_ftt: "ПМИ ↔ ФТТ (явная пара)",
};

export function comparisonKindLabel(kind: string): string {
  return LABELS[kind as ComparisonKind] ?? kind;
}

export function formatRunDate(iso: string): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.slice(0, 10);
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
