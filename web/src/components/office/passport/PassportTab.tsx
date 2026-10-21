import type { OfficeProject } from "@/components/office/officeApi";

// Заглушка вкладки «Паспорт». Заполняет таск 02 в этой папке.
// Контракт: project уже загружен оболочкой; после правки паспорта вызвать
// onProjectChange(project), чтобы шапка проекта обновилась без перезагрузки.
export interface PassportTabProps {
  project: OfficeProject;
  onProjectChange: (project: OfficeProject) => void;
}

export default function PassportTab(_props: PassportTabProps) {
  return (
    <p className="text-sm text-[var(--fg-muted)]">
      Паспорт проекта появится в следующем шаге.
    </p>
  );
}
