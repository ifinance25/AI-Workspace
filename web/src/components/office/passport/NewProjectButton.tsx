// Заглушка кнопки «Новый проект». Форму паспорта и создание проекта добавляет
// таск 02 в этой папке; оболочка (OfficeProjectList) остаётся без правок.
// Контракт: после создания вызвать onCreated(id), оболочка откроет /office/:id.
export interface NewProjectButtonProps {
  onCreated: (id: number) => void;
}

export default function NewProjectButton(_props: NewProjectButtonProps) {
  return (
    <button
      type="button"
      disabled
      title="Создание проекта появится в следующем шаге"
      className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
    >
      Новый проект
    </button>
  );
}
