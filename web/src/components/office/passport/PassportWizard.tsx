import { useEffect, useRef, useState } from "react";
import {
  NATURES, passportApi, WORK_KINDS, type PassportInput,
} from "@/components/office/passport/passportApi";
import TypeChoice from "@/components/office/passport/TypeChoice";

// Мастер паспорта нового проекта. Черновик живёт в localStorage и
// дописывается после перезагрузки; ключ идемпотентности рождается вместе с
// черновиком, поэтому повторное «Создать» не создаёт второй проект.
const DRAFT_KEY = "office.passportDraft";

function newKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function emptyDraft(): PassportInput {
  return {
    name: "", work_kind: "", nature: "", description: "", project_type: "",
    request_key: newKey(),
  };
}

function loadDraft(): PassportInput {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (raw) return { ...emptyDraft(), ...(JSON.parse(raw) as Partial<PassportInput>) };
  } catch {
    // Повреждённый или недоступный черновик: начинаем с пустого.
  }
  return emptyDraft();
}

function saveDraft(draft: PassportInput | null) {
  try {
    if (draft) localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    else localStorage.removeItem(DRAFT_KEY);
  } catch {
    // Без хранилища мастер работает, просто без черновика.
  }
}

const FIELD =
  "w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-hover)] px-3 py-1.5 text-sm";

export interface PassportWizardProps {
  onCreated: (id: number) => void;
  onCancel: () => void;
}

export default function PassportWizard({ onCreated, onCancel }: PassportWizardProps) {
  const [draft, setDraft] = useState<PassportInput>(loadDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sending = useRef(false);

  useEffect(() => {
    saveDraft(draft);
  }, [draft]);

  const set = (field: keyof PassportInput) => (value: string) =>
    setDraft((d) => ({ ...d, [field]: value }));

  const ready = draft.name.trim() !== "" && draft.work_kind !== "" && draft.nature !== "";

  async function submit() {
    if (sending.current || !ready) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    try {
      const project = await passportApi.createProject(draft);
      saveDraft(null);
      onCreated(project.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-sidebar)] p-4">
      <h2 className="text-base font-semibold">Паспорт нового проекта</h2>
      <label className="block text-sm">
        <span className="mb-1 block">Название</span>
        <input
          aria-label="Название"
          className={FIELD}
          value={draft.name}
          onChange={(e) => set("name")(e.target.value)}
        />
      </label>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block">Вид работ</span>
          <select
            aria-label="Вид работ"
            className={FIELD}
            value={draft.work_kind}
            onChange={(e) => set("work_kind")(e.target.value)}
          >
            <option value="">Выберите</option>
            {Object.entries(WORK_KINDS).map(([k, label]) => (
              <option key={k} value={k}>{label}</option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block">Характер</span>
          <select
            aria-label="Характер"
            className={FIELD}
            value={draft.nature}
            onChange={(e) => set("nature")(e.target.value)}
          >
            <option value="">Выберите</option>
            {Object.entries(NATURES).map(([k, label]) => (
              <option key={k} value={k}>{label}</option>
            ))}
          </select>
        </label>
      </div>
      <label className="block text-sm">
        <span className="mb-1 block">Короткое описание</span>
        <textarea
          aria-label="Короткое описание"
          className={FIELD}
          rows={2}
          value={draft.description}
          onChange={(e) => set("description")(e.target.value)}
        />
      </label>
      <TypeChoice
        workKind={draft.work_kind}
        nature={draft.nature}
        description={draft.description}
        value={draft.project_type}
        onChange={set("project_type")}
      />
      {!draft.project_type && ready && (
        <p className="text-xs text-[var(--fg-muted)]">
          Без типа проект сохранится черновиком и не стартует.
        </p>
      )}
      {error && (
        <div className="rounded-xl bg-red-900/30 px-3 py-2 text-sm text-red-300">{error}</div>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={!ready || busy}
          className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
        >
          Создать
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm"
        >
          Отмена
        </button>
      </div>
    </div>
  );
}
