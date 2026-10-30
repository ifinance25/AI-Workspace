import { useState } from "react";
import PassportWizard from "@/components/office/passport/PassportWizard";

// Кнопка «Новый проект» открывает мастер паспорта. Контракт оболочки:
// после создания вызвать onCreated(id), оболочка откроет /office/:id.
export interface NewProjectButtonProps {
  onCreated: (id: number) => void;
}

export default function NewProjectButton({ onCreated }: NewProjectButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white"
      >
        Новый проект
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Новый проект"
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 sm:items-center"
        >
          <div className="w-full max-w-lg">
            <PassportWizard
              onCreated={(id) => {
                setOpen(false);
                onCreated(id);
              }}
              onCancel={() => setOpen(false)}
            />
          </div>
        </div>
      )}
    </>
  );
}
