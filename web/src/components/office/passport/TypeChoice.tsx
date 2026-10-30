import { useEffect, useState } from "react";
import { passportApi, TYPES, type TypeSuggestion } from "@/components/office/passport/passportApi";

// Предложение платформы (тип и одна фраза почему) и выбор менеджера.
// Ничего не выбрано заранее: умолчание выбором не считается.
export interface TypeChoiceProps {
  workKind: string;
  nature: string;
  description: string;
  value: string;
  onChange: (projectType: string) => void;
  disabled?: boolean;
}

export default function TypeChoice({
  workKind, nature, description, value, onChange, disabled,
}: TypeChoiceProps) {
  const [suggestion, setSuggestion] = useState<TypeSuggestion | null>(null);

  useEffect(() => {
    if (!workKind || !nature) {
      setSuggestion(null);
      return;
    }
    let alive = true;
    passportApi.suggestType({ work_kind: workKind, nature, description }).then(
      (s) => {
        if (alive) setSuggestion(s);
      },
      () => {
        if (alive) setSuggestion(null);
      },
    );
    return () => {
      alive = false;
    };
  }, [workKind, nature, description]);

  return (
    <fieldset className="space-y-2" disabled={disabled}>
      <legend className="mb-1 text-sm font-medium">Тип проекта</legend>
      {suggestion && (
        <div className="rounded-lg bg-[var(--bg-hover)] px-3 py-2 text-sm">
          <p>
            Платформа предлагает: <b>{TYPES[suggestion.project_type].toLowerCase()}</b>
          </p>
          <p className="text-[var(--fg-muted)]">{suggestion.reason}</p>
          {value !== suggestion.project_type && (
            <button
              type="button"
              onClick={() => onChange(suggestion.project_type)}
              className="mt-2 rounded-lg bg-[var(--accent)] px-3 py-1 text-xs font-medium text-white"
            >
              Согласиться: {TYPES[suggestion.project_type].toLowerCase()}
            </button>
          )}
        </div>
      )}
      <div className="flex gap-4 text-sm">
        {Object.entries(TYPES).map(([key, label]) => (
          <label key={key} className="flex items-center gap-1.5">
            <input
              type="radio"
              name="project_type"
              value={key}
              checked={value === key}
              onChange={() => onChange(key)}
            />
            {label}
          </label>
        ))}
      </div>
      <p className="text-xs text-[var(--fg-muted)]">
        Маленький: паспорт, бриф, задачи. Крупный: ещё дерево работ, оценки, бюджет и график.
      </p>
    </fieldset>
  );
}
