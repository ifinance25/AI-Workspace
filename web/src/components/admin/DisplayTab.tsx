import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import type { DisplaySettingsAdmin } from "@/lib/types";

export default function DisplayTab() {
  const { refresh } = useAuth();
  const [settings, setSettings] = useState<DisplaySettingsAdmin | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setSettings(await api.adminGetDisplay());
        setError(null);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, []);

  const patch = async (next: Partial<DisplaySettingsAdmin>) => {
    if (!settings) return;
    const merged = { ...settings, ...next };
    setSettings(merged);
    setSaving(true);
    setError(null);
    try {
      const saved = await api.adminPatchDisplay(next);
      setSettings(saved);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
      try {
        setSettings(await api.adminGetDisplay());
      } catch {
        // ignore reload failure
      }
    } finally {
      setSaving(false);
    }
  };

  if (settings === null && !error) {
    return <p className="text-sm text-[var(--fg-muted)]">Загрузка…</p>;
  }

  return (
    <div className="space-y-6">
      {error && (
        <div className="rounded-xl bg-red-900/30 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      <section>
        <h2 className="mb-1 text-base font-medium">Чат</h2>
        <p className="mb-4 text-sm text-[var(--fg-secondary)]">
          Компактный расход за сессию всегда в шапке чата. Подробная строка под
          каждым ответом управляется здесь и тем же флагом, что «Токены» в
          Telegram.
        </p>

        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--border-subtle)] p-4">
          <input
            type="checkbox"
            className="mt-1"
            disabled={saving || settings === null}
            checked={settings?.show_token_usage ?? true}
            onChange={(e) => void patch({ show_token_usage: e.target.checked })}
          />
          <span>
            <span className="block text-sm font-medium">
              Детализация токенов под ответами в чате
            </span>
            <span className="mt-1 block text-[13px] text-[var(--fg-muted)]">
              tokens, in/out, cache, доля контекста, время и стоимость хода.
            </span>
          </span>
        </label>

        <p className="mt-4 text-[13px] text-[var(--fg-muted)]">
          Изменение действует сразу для всех пользователей до перезапуска
          сервиса. Чтобы сохранить навсегда, задайте{" "}
          <code className="rounded bg-[var(--bg-hover)] px-1">display.show_token_usage</code>{" "}
          в <code className="rounded bg-[var(--bg-hover)] px-1">config/config.yaml</code>.
        </p>
      </section>
    </div>
  );
}
