import type { OfficeProject } from "@/components/office/officeApi";

// Заглушка вкладки «Бриф». Заполняет таск 03 в этой папке.
export interface BriefTabProps {
  project: OfficeProject;
}

export default function BriefTab(_props: BriefTabProps) {
  return (
    <p className="text-sm text-[var(--fg-muted)]">Бриф появится в следующем шаге.</p>
  );
}
