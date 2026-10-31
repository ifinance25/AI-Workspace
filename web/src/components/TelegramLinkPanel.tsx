import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import type { TelegramLinkStatus } from "@/lib/types";

const card =
  "rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-sidebar)] p-4 text-sm";
const button =
  "rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm text-[var(--fg-secondary)] hover:text-[var(--fg-primary)] disabled:opacity-50";

// Привязка Telegram к учётке: вход без пароля и канал уведомлений.
export default function TelegramLinkPanel() {
  const [info, setInfo] = useState<TelegramLinkStatus | null>(null);
  const [deepLink, setDeepLink] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setInfo(await api.telegramStatus());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
    // Человек возвращается из Telegram на эту вкладку: шаг мог измениться.
    const onFocus = () => void load();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const start = () =>
    run(async () => {
      const { deep_link } = await api.telegramStart();
      setDeepLink(deep_link);
      await load();
    });

  const confirm = () =>
    run(async () => {
      await api.telegramConfirm(password);
      setPassword("");
      setDeepLink("");
      await load();
    });

  const cancel = () =>
    run(async () => {
      await api.telegramUnbind();
      setDeepLink("");
      await load();
    });

  // Отвязка закрывает все сессии учётки, эту тоже.
  const unbind = () =>
    run(async () => {
      await api.telegramUnbind();
      window.location.assign("/login");
    });

  if (!info) {
    return error ? <p className="text-sm text-red-400">{error}</p> : null;
  }

  if (!info.available && info.state !== "active") {
    return (
      <div className={card}>
        <p className="text-[var(--fg-muted)]">
          Привязка недоступна: нужна учётка с паролем и запущенный бот.
        </p>
      </div>
    );
  }

  return (
    <div className={`${card} space-y-3`}>
      {info.state === "active" && (
        <>
          <p className="text-[var(--fg-primary)]">Привязан аккаунт: {info.username}</p>
          <p className="text-[var(--fg-muted)]">
            Отвязка завершит все ваши сессии, войти снова можно по паролю.
          </p>
          <button className={button} disabled={busy} onClick={() => void unbind()}>
            Отвязать
          </button>
        </>
      )}

      {info.state === "none" && (
        <>
          <p className="text-[var(--fg-muted)]">
            Привяжите Telegram, чтобы входить без пароля и получать уведомления.
          </p>
          <button className={button} disabled={busy} onClick={() => void start()}>
            Привязать Telegram
          </button>
        </>
      )}

      {info.state === "waiting_start" && (
        <>
          <p className="text-[var(--fg-muted)]">
            Откройте бота, нажмите «Запустить» и вернитесь сюда. Ссылка живёт 10 минут.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {deepLink ? (
              <a className={button} href={deepLink} target="_blank" rel="noopener noreferrer">
                Открыть бота
              </a>
            ) : (
              <button className={button} disabled={busy} onClick={() => void start()}>
                Получить новую ссылку
              </button>
            )}
            <button className={button} disabled={busy} onClick={() => void load()}>
              Проверить
            </button>
            <button className={button} disabled={busy} onClick={() => void start()}>
              Начать заново
            </button>
          </div>
        </>
      )}

      {info.state === "waiting_confirm" && (
        <>
          <p className="text-[var(--fg-primary)]">
            Бот получил аккаунт: {info.username} (id {info.external_user_id}).
          </p>
          <p className="text-[var(--fg-muted)]">
            Это ваш Telegram? Введите пароль учётки. Если аккаунт чужой, нажмите «Отменить».
          </p>
          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void confirm();
            }}
          >
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Пароль"
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-3 py-1.5 text-sm text-[var(--fg-primary)]"
            />
            <button type="submit" className={button} disabled={busy || !password}>
              Подтвердить
            </button>
            <button
              type="button"
              className={button}
              disabled={busy}
              onClick={() => void cancel()}
            >
              Отменить
            </button>
          </form>
        </>
      )}

      {error && <p className="text-red-400">{error}</p>}
    </div>
  );
}
