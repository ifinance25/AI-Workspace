import type { OfficeProject } from "@/components/office/officeApi";

// Заглушка вкладки «Задание». Заполняет таск 04 в этой папке.
export interface SpecTabProps {
  project: OfficeProject;
}

export default function SpecTab(_props: SpecTabProps) {
  return (
    <p className="text-sm text-[var(--fg-muted)]">Задание появится в следующем шаге.</p>
  );
}
