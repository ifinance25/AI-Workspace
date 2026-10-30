import { useState } from "react";
import type { OfficeProject } from "@/components/office/officeApi";
import { NATURES, passportApi, WORK_KINDS } from "@/components/office/passport/passportApi";
import TypeChoice from "@/components/office/passport/TypeChoice";

// Вкладка «Паспорт»: поля паспорта, статус словами и выбор типа.
// Тип меняется, пока заказчик не принял версию задания; запрет решает сервер.
export interface PassportTabProps {
  project: OfficeProject;
  onProjectChange: (project: OfficeProject) => void;
}

// Текст отказа: сервер кладёт его в JSON {detail}, клиент в ApiError.message.
function errorText(e: unknown): string {
  const message = e instanceof Error ? e.message : String(e);
  const json = message.indexOf("{");
  if (json >= 0) {
    try {
      const detail = (JSON.parse(message.slice(json)) as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
    } catch {
      // Не JSON: показываем как есть.
    }
  }
  return message;
}

export default function PassportTab({ project, onProjectChange }: PassportTabProps) {
  const [choice, setChoice] = useState(project.project_type);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isDraft = project.project_type === "";

  async function saveType() {
    if (busy || !choice) return;
    setBusy(true);
    setError(null);
    try {
      onProjectChange(await passportApi.setType(project.id, choice));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {isDraft && (
        <div className="rounded-lg bg-amber-900/30 px-3 py-2 text-sm text-amber-200">
          Черновик: тип проекта не выбран, проект не стартовал. Выберите тип ниже.
        </div>
      )}
      <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
        <dt className="text-[var(--fg-muted)]">Вид работ</dt>
        <dd>{WORK_KINDS[project.work_kind] ?? "не указан"}</dd>
        <dt className="text-[var(--fg-muted)]">Характер</dt>
        <dd>{NATURES[project.nature] ?? "не указан"}</dd>
        <dt className="text-[var(--fg-muted)]">Описание</dt>
        <dd className="whitespace-pre-wrap">{project.description || "нет"}</dd>
      </dl>
      <TypeChoice
        workKind={project.work_kind}
        nature={project.nature}
        description={project.description ?? ""}
        value={choice}
        onChange={setChoice}
        disabled={busy}
      />
      {error && (
        <div className="rounded-xl bg-red-900/30 px-3 py-2 text-sm text-red-300">{error}</div>
      )}
      <button
        type="button"
        onClick={saveType}
        disabled={busy || !choice || choice === project.project_type}
        className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
      >
        Сохранить тип
      </button>
    </div>
  );
}
