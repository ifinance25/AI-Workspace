import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";

type RedmineAccount = {
  base_url: string;
  redmine_project: string;
  has_token: boolean;
  last4: string;
};

export default function RedmineTab() {
  const [account, setAccount] = useState<RedmineAccount | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [project, setProject] = useState("");
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const row = await api.adminGetRedmine();
      setAccount(row);
      setBaseUrl(row.base_url);
      setProject(row.redmine_project);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const row = await api.adminPutRedmine({
        base_url: baseUrl,
        redmine_project: project,
        api_key: token.trim() ? token : null,
      });
      setAccount(row);
      setToken("");
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-[var(--fg-muted)]">Загрузка…</p>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="mb-1 text-base font-medium">Redmine</h2>
        <p className="text-sm text-[var(--fg-secondary)]">
          Токен хранится на сервере. После сохранения страница его больше не показывает.
        </p>
      </div>
      {error && <div className="alert-error">{error}</div>}
      {saved && (
        <div className="alert-success">
          Сохранено{account?.has_token ? `, ключ оканчивается на ${account.last4}` : ""}.
        </div>
      )}
      <label className="block text-sm">
        <span className="mb-1 block text-[var(--fg-secondary)]">Адрес Redmine</span>
        <input
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://redmine.studiofact.ru"
          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-3 py-2"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-[var(--fg-secondary)]">Проект в Redmine</span>
        <input
          value={project}
          onChange={(e) => setProject(e.target.value)}
          placeholder="HR-платформа_Заявка 2"
          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-3 py-2"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-[var(--fg-secondary)]">Токен API</span>
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          autoComplete="off"
          placeholder={account?.has_token ? "сохранён, введите новый чтобы заменить" : "ключ API"}
          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-3 py-2"
        />
      </label>
      <button
        type="button"
        onClick={() => void submit()}
        disabled={saving}
        className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm disabled:opacity-50"
      >
        {saving ? "Сохраняю…" : "Сохранить"}
      </button>
    </div>
  );
}
