import { useEffect, useState } from "react";
import { errorText, runsApi } from "@/components/runs/runsApi";

const TOKEN_KEY = (projectId: number) => `office.runs.redmineToken.${projectId}`;

interface Props {
  projectId: number;
  runId: number;
  runKey: string;
  confirmedCount: number;
  open: boolean;
  onClose: () => void;
  onExported: (issueUrl: string) => void;
}

export default function RedmineStandRemediationModal({
  projectId,
  runId,
  runKey,
  confirmedCount,
  open,
  onClose,
  onExported,
}: Props) {
  const [token, setToken] = useState("");
  const [remember, setRemember] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    try {
      const saved = sessionStorage.getItem(TOKEN_KEY(projectId));
      if (saved) setToken(saved);
    } catch {
      /* ignore */
    }
  }, [open, projectId]);

  if (!open) return null;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await runsApi.exportStandRemediation(projectId, runId, {
        api_key: token.trim(),
        request_key: `run-${runId}-stand-remediation`,
      });
      if (remember) {
        try {
          sessionStorage.setItem(TOKEN_KEY(projectId), token.trim());
        } catch {
          /* ignore */
        }
      }
      onExported(result.issue_url);
      onClose();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal
      aria-label="Тикет на исправление стенда"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md space-y-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-4 shadow-lg"
        onClick={(event) => event.stopPropagation()}
      >
        <h3 className="text-lg font-semibold">Тикет Redmine на исправление стенда</h3>
        <p className="text-sm text-[var(--fg-secondary)]">
          Прогон {runKey} можно закрыть. Будет создана одна сводная задача с{" "}
          {confirmedCount} подтверждёнными дефектами стенда. Ключ API не сохраняется на сервере.
        </p>
        <input
          aria-label="Ключ API Redmine"
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          className="w-full rounded-lg border border-[var(--border-subtle)] bg-transparent px-2 py-1.5 text-sm"
          placeholder="Ключ API Redmine"
        />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          Запомнить ключ в этой вкладке браузера
        </label>
        {error && (
          <p role="alert" className="alert-error">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm">
            Позже
          </button>
          <button
            type="button"
            disabled={busy || !token.trim()}
            onClick={() => void submit()}
            className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm text-white disabled:opacity-40"
          >
            Создать задачу
          </button>
        </div>
      </div>
    </div>
  );
}
