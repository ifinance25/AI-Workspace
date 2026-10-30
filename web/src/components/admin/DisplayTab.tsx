import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import type { DisplaySettingsAdmin } from "@/lib/types";

export default function DisplayTab() {
  const { refresh } = useAuth();
  const [settings, setSettings] = useState<DisplaySettingsAdmin | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSettings(await api.adminGetDisplay());
    } catch (e) {
      setSettings(null);
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const patch = async (next: Partial<DisplaySettingsAdmin>) => {
    if (!settings) return;
    const prev = settings;
    const merged = { ...settings, ...next };
    setSettings(merged);
    setSaving(true);
    setError(null);
    try {
      const saved = await api.adminPatchDisplay(next);
      setSettings(saved);
      await refresh();
    } catch (e) {
      setSettings(prev);
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-[var(--fg-muted)]">Загрузка…</p>;
  }

  const controlsDisabled = saving || settings === null;

  return (
    <div className="space-y-6">
      {error && (
        <div className="space-y-2 rounded-xl bg-red-900/30 px-3 py-2 text-sm text-red-300">
          <p>{error}</p>
          {settings === null && (
            <button
              type="button"
              onClick={() => void load()}
              className="rounded-lg bg-red-950/40 px-2 py-1 text-xs text-red-200 hover:bg-red-950/60"
            >
              Повторить загрузку
            </button>
          )}
        </div>
      )}

      <section>
        <h2 className="mb-1 text-base font-medium text-[var(--fg-primary)]">Чат</h2>
        <p className="mb-4 text-sm text-[var(--fg-secondary)]">
          Компактный расход за сессию всегда в шапке чата. Подробная строка под
          каждым ответом управляется здесь и тем же флагом, что «Токены» в
          Telegram.
        </p>

        <label
          className={`flex items-start gap-3 rounded-xl border border-[var(--border-subtle)] p-4 ${
            controlsDisabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"
          }`}
        >
          <input
            type="checkbox"
            className="mt-1 shrink-0"
            disabled={controlsDisabled}
            checked={settings?.show_token_usage ?? true}
            onChange={(e) => void patch({ show_token_usage: e.target.checked })}
          />
          <span className="min-w-0 text-[var(--fg-primary)]">
            <span className="block text-sm font-medium">
              Детализация токенов под ответами в чате
            </span>
            <span className="mt-1 block text-[13px] leading-snug text-[var(--fg-muted)]">
              tokens, in/out, cache, доля контекста, время и стоимость хода.
            </span>
          </span>
        </label>

        <p className="mt-4 text-[13px] text-[var(--fg-muted)]">
          Изменение действует сразу для всех пользователей до перезапуска
          сервиса. Чтобы сохранить навсегда, задайте{" "}
          <code className="rounded bg-[var(--bg-hover)] px-1 text-[var(--fg-secondary)]">
            display.show_token_usage
          </code>{" "}
          в{" "}
          <code className="rounded bg-[var(--bg-hover)] px-1 text-[var(--fg-secondary)]">
            config/config.yaml
          </code>
          .
        </p>
      </section>
    </div>
  );
}
