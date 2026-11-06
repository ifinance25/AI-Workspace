export type FindingCardTab = "essence" | "documents" | "pdf" | "history";

export const FINDING_CARD_TABS: Array<{ id: FindingCardTab; label: string }> = [
  { id: "essence", label: "Суть несоответствия" },
  { id: "documents", label: "Документы" },
  { id: "pdf", label: "Документ (PDF)" },
  { id: "history", label: "История решений" },
];

export interface PdfViewState {
  name: string;
  page: number | null;
}

/** Переключение на вкладку PDF и открытие указанной страницы. */
export function openPdfInFindingCard(
  pdfName: string,
  page: number | null | undefined,
): { tab: FindingCardTab; pdf: PdfViewState } {
  return {
    tab: "pdf",
    pdf: { name: pdfName, page: page ?? null },
  };
}
