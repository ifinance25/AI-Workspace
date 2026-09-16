import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { SshProfileInfo } from "@/lib/types";

const empty: SshProfileInfo = {
  enabled: true,
  configured: false,
  host: "",
  port: 22,
  username: "",
  has_key: false,
  fingerprint: null,
};

export default function SshSettingsPanel() {
  const [info, setInfo] = useState<SshProfileInfo | null>(null);
  const [host, setHost] = useState("");
  const [port, setPort] = useState("22");
  const [username, setUsername] = useState("");
  const [privateKey, setPrivateKey] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const load = async () => {
    try {
      const next = await api.getSsh();
      setInfo(next);
      setHost(next.host);
      setPort(String(next.port || 22));
      setUsername(next.username);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const onSave = async () => {
    const portNum = Number(port);
    if (!host.trim() || !username.trim()) {
      setError("Укажите адрес сервера и имя пользователя");
      return;
    }
    if (!Number.isInteger(portNum) || portNum < 1 || portNum > 65535) {
      setError("Порт должен быть числом от 1 до 65535");
      return;
    }
    if (!info?.has_key && !privateKey.trim()) {
      setError("Вставьте закрытый SSH-ключ");
      return;
    }
    setBusy(true);
    setSaved(false);
    setError(null);
    try {
      const body: {
        host: string;
        port: number;
        username: string;
        private_key?: string;
        passphrase?: string;
      } = {
        host: host.trim(),
        port: portNum,
        username: username.trim(),
      };
      if (privateKey.trim()) body.private_key = privateKey.trim();
      if (passphrase) body.passphrase = passphrase;
      const next = await api.saveSsh(body);
      setInfo(next);
      setPrivateKey("");
      setPassphrase("");
      setSaved(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async () => {
    setBusy(true);
    setSaved(false);
    setError(null);
    try {
      await api.deleteSsh();
      setInfo({ ...empty, enabled: info?.enabled ?? true });
      setHost("");
      setPort("22");
      setUsername("");
      setPrivateKey("");
      setPassphrase("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (info === null && !error) {
    return <div className="text-sm text-[var(--fg-muted)]">Загрузка…</div>;
  }

  if (info && !info.enabled) {
    return (
      <div className="text-sm text-[var(--fg-muted)]">
        Терминал SSH выключен на сервере (не задан ключ шифрования). Обратитесь к
        администратору.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--fg-muted)]">
        Панель подключается к серверу по SSH вашим ключом. Закрытый ключ хранится
        в зашифрованном виде и в браузер больше не возвращается.
      </p>
      {error && (
        <div className="rounded-lg bg-red-900/30 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}
      {saved && (
        <div className="rounded-lg bg-emerald-900/20 px-3 py-2 text-sm text-emerald-300">
          Сохранено. Откройте «Терминал» в боковой панели.
        </div>
      )}
      <label className="block space-y-1.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
          Адрес сервера
        </span>
        <input
          value={host}
          onChange={(e) => setHost(e.target.value)}
          placeholder="ai-panel.duckdns.org"
          autoComplete="off"
          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-sm text-[var(--fg-primary)] focus:outline-none"
        />
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="block space-y-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
            Порт
          </span>
          <input
            value={port}
            onChange={(e) => setPort(e.target.value)}
            inputMode="numeric"
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-sm text-[var(--fg-primary)] focus:outline-none"
          />
        </label>
        <label className="block space-y-1.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
            Пользователь
          </span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="ubuntu"
            autoComplete="off"
            className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-sm text-[var(--fg-primary)] focus:outline-none"
          />
        </label>
      </div>
      <label className="block space-y-1.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
          Закрытый SSH-ключ
        </span>
        {info?.has_key && (
          <div className="text-xs text-[var(--fg-secondary)]">
            Ключ уже сохранён
            {info.fingerprint ? ` (${info.fingerprint})` : ""}. Вставьте новый,
            чтобы заменить.
          </div>
        )}
        <textarea
          value={privateKey}
          onChange={(e) => setPrivateKey(e.target.value)}
          rows={7}
          spellCheck={false}
          placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
          className="w-full resize-y rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 font-mono text-xs text-[var(--fg-primary)] focus:outline-none"
        />
      </label>
      <label className="block space-y-1.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
          Парольная фраза ключа (если есть)
        </span>
        <input
          type="password"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          autoComplete="new-password"
          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-sm text-[var(--fg-primary)] focus:outline-none"
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void onSave()}
          disabled={busy}
          className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[var(--accent-fg)] disabled:opacity-50"
        >
          Сохранить
        </button>
        {info?.configured && (
          <button
            type="button"
            onClick={() => void onDelete()}
            disabled={busy}
            className="rounded-lg px-4 py-2 text-sm text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
          >
            Удалить ключ
          </button>
        )}
      </div>
    </div>
  );
}
