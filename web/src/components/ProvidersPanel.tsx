import { useEffect, useState } from "react";
import { api, ApiError } from "@/api/client";
import type { LlmProvider, ProvidersInfo } from "@/lib/types";
import { ClaudeLogo, OpenAILogo, providerLogo } from "@/components/icons";

interface Props {
  privileged: boolean;
}

function humanError(e: unknown): string {
  const msg = (e as Error)?.message ?? String(e);
  const brace = msg.indexOf("{");
  if (brace !== -1) {
    try {
      const parsed = JSON.parse(msg.slice(brace)) as { detail?: unknown };
      if (typeof parsed.detail === "string") return parsed.detail;
    } catch {
      /* fall through */
    }
  }
  return msg;
}

function statusBadge(status: string | null, last4: string | null, prefix = "…") {
  if (!status || !last4) {
    return <span className="text-[var(--fg-primary)]">не задан</span>;
  }
  const label =
    status === "active"
      ? "активен"
      : status === "needs_reentry"
        ? "нужен повторный ввод"
        : "не проверен";
  const cls =
    status === "active"
      ? "bg-emerald-900/30 text-emerald-300"
      : status === "needs_reentry"
        ? "bg-red-900/30 text-red-300"
        : "bg-amber-900/30 text-amber-300";
  return (
    <span className="flex items-center gap-2">
      <span className="font-mono text-[var(--fg-primary)]">
        {prefix}
        {last4}
      </span>
      <span className={`rounded-full px-2 py-0.5 text-[11px] ${cls}`}>{label}</span>
    </span>
  );
}

function keyFieldLabel(p: LlmProvider): string {
  if (p.id === "claude") {
    return p.connected ? "Заменить ключ Anthropic" : "API-ключ Anthropic";
  }
  if (p.id === "openai") {
    return p.connected ? "Заменить ключ OpenAI" : "API-ключ OpenAI";
  }
  return p.connected ? "Заменить ключ" : "API-ключ";
}

function ProviderMark({ id, size = 18 }: { id: string; size?: number }) {
  if (id === "claude") return <ClaudeLogo size={size} />;
  if (id === "openai") return <OpenAILogo size={size} />;
  return providerLogo(id, size);
}

export default function ProvidersPanel({ privileged }: Props) {
  const [info, setInfo] = useState<ProvidersInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [oauthDrafts, setOauthDrafts] = useState<Record<string, string>>({});
  const [baseDrafts, setBaseDrafts] = useState<Record<string, string>>({});
  const [savingId, setSavingId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.listProviders();
      setInfo(data);
      setError(null);
      setDisabled(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 501) {
        setDisabled(true);
      } else {
        setError(humanError(e));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveKey = async (p: LlmProvider, kind: "api_key" | "oauth") => {
    const raw =
      kind === "oauth" ? oauthDrafts[p.id]?.trim() : drafts[p.id]?.trim();
    setSuccess(null);
    if (!raw) {
      setError("Введите ключ");
      return;
    }
    if (kind === "api_key" && p.id === "claude" && !raw.startsWith("sk-ant-")) {
      setError("Ключ должен начинаться с sk-ant-");
      return;
    }
    setSavingId(p.id);
    setError(null);
    try {
      const body =
        kind === "oauth"
          ? { oauth_token: raw }
          : {
              api_key: raw,
              ...(p.base_url_editable && baseDrafts[p.id]?.trim()
                ? { base_url: baseDrafts[p.id].trim() }
                : {}),
            };
      const res = await api.putProvider(p.id, body);
      if (kind === "oauth") {
        setOauthDrafts((d) => ({ ...d, [p.id]: "" }));
      } else {
        setDrafts((d) => ({ ...d, [p.id]: "" }));
      }
      setSuccess(
        res.warning
          ? `${res.message ?? "API key saved"}. ${res.warning}`
          : (res.message ?? "API key saved"),
      );
      await load();
    } catch (e) {
      setError(humanError(e));
    } finally {
      setSavingId(null);
    }
  };

  const removeKey = async (p: LlmProvider) => {
    setSuccess(null);
    setError(null);
    setSavingId(p.id);
    try {
      const res = await api.deleteProvider(p.id);
      setSuccess(res.message);
      await load();
    } catch (e) {
      setError(humanError(e));
    } finally {
      setSavingId(null);
    }
  };

  const pickModel = async (p: LlmProvider, modelId: string) => {
    setSavingId(p.id);
    setError(null);
    setSuccess(null);
    try {
      await api.setActiveProvider(p.id, modelId);
      if (p.id === "claude") {
        try {
          await api.patchModel(modelId);
        } catch {
          /* не-админ: модель остаётся в личных настройках */
        }
      }
      await load();
    } catch (e) {
      setError(humanError(e));
    } finally {
      setSavingId(null);
    }
  };

  if (disabled) {
    return (
      <div className="text-sm text-[var(--fg-muted)]">
        Управление ключом выключено на сервере (не задан ключ шифрования).
        Обратитесь к администратору.
      </div>
    );
  }

  const effectivePrivileged = info?.privileged ?? privileged;

  return (
    <div className="space-y-5">
      <p className="text-sm text-[var(--fg-muted)]">
        Подключите провайдера, где есть баланс. Активная модель: та, которую
        выберете в группе. Агент с файлами и терминалом работает через Claude
        Code: Claude и Kimi сразу, OpenAI и Cursor при Anthropic-прокси.
      </p>
      {effectivePrivileged && (
        <p className="text-sm text-[var(--fg-muted)]">
          Необязательно для Claude: по умолчанию подписка сервиса; задайте свой
          ключ, чтобы платить им.
        </p>
      )}
      {!effectivePrivileged && (
        <p className="text-sm text-[var(--fg-muted)]">
          Без ключа отправка сообщений недоступна.
        </p>
      )}

      {error && (
        <div className="rounded-xl border border-red-700/40 bg-red-900/20 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}
      {success && (
        <div className="rounded-xl border border-emerald-700/40 bg-emerald-900/20 px-3 py-2 text-sm text-emerald-300">
          {success}
        </div>
      )}

      {loading && !info ? (
        <div className="text-sm text-[var(--fg-muted)]">Загрузка…</div>
      ) : (
        info?.providers.map((p) => {
          const busy = savingId === p.id;
          return (
            <section
              key={p.id}
              className={`rounded-2xl border p-4 ${
                p.active
                  ? "border-[var(--border-subtle)] bg-[var(--bg-hover)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-sidebar)]"
              }`}
            >
              <header className="mb-3 flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <ProviderMark id={p.id} />
                  <div>
                    <div className="text-sm font-semibold text-[var(--fg-primary)]">
                      {p.label}
                      {p.active && (
                        <span className="ml-2 text-[11px] font-medium text-emerald-400">
                          используется
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-[var(--fg-muted)]">{p.description}</div>
                  </div>
                </div>
              </header>

              {p.oauth_url && (
                <div className="mb-3 space-y-2">
                  <a
                    href={p.oauth_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex rounded-lg bg-[var(--accent)] px-3 py-2 text-sm font-medium text-[var(--bg-canvas)]"
                  >
                    {p.oauth_label || "Подключить подписку"}
                  </a>
                  <input
                    type="password"
                    autoComplete="off"
                    value={oauthDrafts[p.id] ?? ""}
                    onChange={(e) =>
                      setOauthDrafts((d) => ({ ...d, [p.id]: e.target.value }))
                    }
                    placeholder="Токен подписки после входа в браузере"
                    disabled={busy}
                    className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 font-mono text-sm text-[var(--fg-primary)] focus:outline-none disabled:opacity-50"
                  />
                  <button
                    onClick={() => void saveKey(p, "oauth")}
                    disabled={busy || !(oauthDrafts[p.id] ?? "").trim()}
                    className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm text-[var(--fg-primary)] disabled:opacity-50"
                  >
                    Сохранить токен
                  </button>
                </div>
              )}

              <div className="mb-3 flex items-center justify-between gap-2 text-sm">
                <span className="text-[var(--fg-muted)]">Текущий ключ</span>
                {statusBadge(
                  p.status,
                  p.last4,
                  p.id === "claude" ? "sk-…" : "…",
                )}
              </div>

              <div className="space-y-2">
                <label
                  htmlFor={`provider-key-${p.id}`}
                  className="block text-[12px] font-semibold uppercase tracking-wider text-[var(--fg-muted)]"
                >
                  {keyFieldLabel(p)}
                </label>
                <input
                  id={`provider-key-${p.id}`}
                  type="password"
                  autoComplete="off"
                  value={drafts[p.id] ?? ""}
                  onChange={(e) =>
                    setDrafts((d) => ({ ...d, [p.id]: e.target.value }))
                  }
                  placeholder={p.key_placeholder}
                  disabled={busy}
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 font-mono text-sm text-[var(--fg-primary)] focus:outline-none disabled:opacity-50"
                />
                {p.base_url_editable && (
                  <input
                    type="url"
                    value={baseDrafts[p.id] ?? p.base_url ?? ""}
                    onChange={(e) =>
                      setBaseDrafts((d) => ({ ...d, [p.id]: e.target.value }))
                    }
                    placeholder="Базовый URL (Anthropic-прокси, необязательно)"
                    disabled={busy}
                    className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 font-mono text-sm text-[var(--fg-primary)] focus:outline-none disabled:opacity-50"
                  />
                )}
                <p className="text-[11px] text-[var(--fg-muted)]">
                  {p.key_hint}{" "}
                  <a
                    href={p.how_to_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[#6ea8fe] underline"
                  >
                    Открыть кабинет
                  </a>
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => void saveKey(p, "api_key")}
                    disabled={busy || !(drafts[p.id] ?? "").trim()}
                    className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[var(--bg-canvas)] disabled:opacity-50"
                  >
                    Сохранить
                  </button>
                  {p.connected && (
                    <button
                      onClick={() => void removeKey(p)}
                      disabled={busy}
                      className="rounded-lg px-4 py-2 text-sm text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)] disabled:opacity-50"
                    >
                      Удалить
                    </button>
                  )}
                </div>
              </div>

              <div className="mt-4 space-y-2">
                <div className="text-[12px] font-semibold uppercase tracking-wider text-[var(--fg-muted)]">
                  Модель по умолчанию
                </div>
                {p.models.map((m) => {
                  const active = p.active && m.id === p.current_model;
                  return (
                    <button
                      key={m.id}
                      onClick={() => void pickModel(p, m.id)}
                      disabled={busy || active}
                      className={`flex w-full items-start gap-3 rounded-2xl border border-[var(--border-subtle)] p-3 text-left transition-colors ${
                        active
                          ? "bg-[var(--bg-canvas)] text-[var(--fg-primary)]"
                          : "text-[var(--fg-secondary)] hover:bg-[var(--bg-canvas)] hover:text-[var(--fg-primary)] disabled:cursor-not-allowed"
                      }`}
                    >
                      <span
                        className={`mt-1.5 inline-block h-2.5 w-2.5 rounded-full ${
                          active ? "bg-emerald-500" : "bg-[var(--bg-hover)]"
                        }`}
                      />
                      <span className="flex-1">
                        <span className="block text-sm font-semibold">{m.label}</span>
                        <span className="mt-0.5 block text-xs text-[var(--fg-muted)]">
                          {m.hint}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
          );
        })
      )}
    </div>
  );
}
