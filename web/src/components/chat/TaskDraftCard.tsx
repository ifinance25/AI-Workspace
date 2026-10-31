import { useState } from "react";
import { Link } from "react-router-dom";
import { officeRequest } from "@/components/office/officeApi";
import type { RedmineIssueResult } from "@/components/redmine/redmineApi";

/** Черновик задачи из ответа чата (блок pm-task). Подпись ставит сервер, не модель. */
export interface TaskDraft {
  project_id: number;
  project: string;
  subject: string;
  description: string;
  due_date: string;
  signature: string;
}

export function parseTaskDraft(raw: string): TaskDraft | null {
  try {
    const data = JSON.parse(raw) as Record<string, unknown>;
    if (
      typeof data.project_id !== "number" ||
      typeof data.subject !== "string" ||
      typeof data.signature !== "string" ||
      !data.subject.trim()
    ) {
      return null;
    }
    return {
      project_id: data.project_id,
      project: typeof data.project === "string" ? data.project : "",
      subject: data.subject,
      description: typeof data.description === "string" ? data.description : "",
      due_date: typeof data.due_date === "string" ? data.due_date : "",
      signature: data.signature,
    };
  } catch {
    return null;
  }
}

const storageKey = (d: TaskDraft) => `pm-task-created:${d.signature}`;

function savedNumber(d: TaskDraft): number | null {
  try {
    const raw = window.localStorage.getItem(storageKey(d));
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}

export default function TaskDraftCard({ draft }: { draft: TaskDraft }) {
  const [created, setCreated] = useState<number | null>(() => savedNumber(draft));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await officeRequest<RedmineIssueResult>(
        "POST",
        `/api/office/projects/${draft.project_id}/redmine/proposals`,
        {
          subject: draft.subject,
          description: draft.description,
          due_date: draft.due_date,
          signature: draft.signature,
        },
      );
      const number = result.issue.id;
      setCreated(number);
      try {
        window.localStorage.setItem(storageKey(draft), String(number));
      } catch {
        /* хранилище закрыто: карточка просто останется без отметки после перезагрузки */
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось создать задачу");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="my-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4"
      data-testid="task-draft-card"
    >
      <div className="text-xs text-[var(--fg-muted)]">
        Черновик задачи Redmine{draft.project ? `, проект «${draft.project}»` : ""}
      </div>
      <div className="mt-1 text-base font-medium text-[var(--fg-primary)]">{draft.subject}</div>
      {draft.description && (
        <div className="mt-2 whitespace-pre-wrap text-sm text-[var(--fg-secondary)]">
          {draft.description}
        </div>
      )}
      {draft.due_date && (
        <div className="mt-2 text-sm text-[var(--fg-secondary)]">Срок: {draft.due_date}</div>
      )}
      <div className="mt-3 flex items-center gap-3">
        {created !== null ? (
          <span className="text-sm text-[var(--fg-primary)]">
            Задача №{created} создана.{" "}
            <Link
              className="text-[var(--accent-brand)] underline"
              to={`/office/${draft.project_id}/redmine`}
            >
              Открыть в разделе задач
            </Link>
          </span>
        ) : (
          <button
            type="button"
            onClick={() => void create()}
            disabled={busy}
            className="rounded-full bg-[var(--accent)] px-4 py-1.5 text-sm text-[var(--accent-fg)] hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Создаю…" : "Создать в Redmine"}
          </button>
        )}
        {error && <span className="text-sm text-red-400">{error}</span>}
      </div>
    </div>
  );
}
