import { useCallback, useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { api } from "@/api/client";
import { openSshWs, type SshWsHandle } from "@/api/sshWs";
import { PanelLeftIcon } from "@/components/icons";
import type { SshProfileInfo } from "@/lib/types";

interface Props {
  onOpenSidebar?: () => void;
  onOpenSettings: () => void;
}

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

export default function TerminalPanel({ onOpenSidebar, onOpenSettings }: Props) {
  const [info, setInfo] = useState<SshProfileInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "connecting" | "ready" | "closed">(
    "idle",
  );
  const [statusText, setStatusText] = useState("Не подключено");
  const hostRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<SshWsHandle | null>(null);
  const sawErrorRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getSsh()
      .then((next) => {
        if (!cancelled) setInfo(next);
      })
      .catch((e) => {
        if (!cancelled) setLoadError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("closed");
    setStatusText("Отключено");
  }, []);

  useEffect(() => () => {
    wsRef.current?.close();
    termRef.current?.dispose();
  }, []);

  const ensureTerm = useCallback(() => {
    if (termRef.current || !hostRef.current) return termRef.current;
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
      theme: {
        background: cssVar("--bg-canvas", "#262624"),
        foreground: cssVar("--fg-primary", "#faf9f5"),
        cursor: cssVar("--accent-brand", "#d97757"),
        selectionBackground: "rgba(217, 119, 87, 0.35)",
      },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(hostRef.current);
    fit.fit();
    term.onData((data) => {
      wsRef.current?.send({ type: "in", data });
    });
    termRef.current = term;
    fitRef.current = fit;
    return term;
  }, []);

  const sendResize = useCallback(() => {
    const term = termRef.current;
    fitRef.current?.fit();
    if (term && wsRef.current) {
      wsRef.current.send({ type: "resize", cols: term.cols, rows: term.rows });
    }
  }, []);

  const connect = useCallback(() => {
    const term = ensureTerm();
    if (!term) return;
    wsRef.current?.close();
    setStatus("connecting");
    setStatusText("Подключение…");
    sawErrorRef.current = false;
    const handle = openSshWs(
      (msg) => {
        if (msg.type === "ready") {
          setStatus("ready");
          setStatusText(`${msg.username}@${msg.host}`);
          sendResize();
          term.focus();
        } else if (msg.type === "out") {
          term.write(msg.data);
        } else if (msg.type === "error") {
          sawErrorRef.current = true;
          setStatus("closed");
          setStatusText(msg.error);
          term.writeln(`\r\n${msg.error}`);
        }
      },
      {
        onClose: (code) => {
          setStatus("closed");
          if (sawErrorRef.current) return;
          if (code === 1008) {
            setStatusText("Нет доступа или SSH не настроен");
          } else {
            setStatusText("Соединение закрыто");
          }
        },
      },
    );
    wsRef.current = handle;
  }, [ensureTerm, sendResize]);

  useEffect(() => {
    if (status !== "ready") return;
    const host = hostRef.current;
    if (!host) return;
    const ro = new ResizeObserver(() => sendResize());
    ro.observe(host);
    return () => ro.disconnect();
  }, [status, sendResize]);

  const readyToConnect = Boolean(info?.enabled && info.configured && info.has_key);

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-[var(--bg-canvas)]">
      <header className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
        {onOpenSidebar && (
          <button
            type="button"
            onClick={onOpenSidebar}
            className="icon-btn flex h-11 w-11 items-center justify-center rounded-xl text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)] lg:hidden"
            aria-label="Открыть список чатов"
            title="Чаты"
          >
            <PanelLeftIcon size={20} />
          </button>
        )}
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-[var(--fg-primary)]">
            Терминал SSH
          </div>
          <div className="truncate text-xs text-[var(--fg-muted)]">{statusText}</div>
        </div>
        {status === "ready" || status === "connecting" ? (
          <button
            type="button"
            onClick={disconnect}
            className="rounded-xl px-3 py-2 text-sm text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
          >
            Отключить
          </button>
        ) : (
          <button
            type="button"
            onClick={connect}
            disabled={!readyToConnect}
            className="rounded-xl bg-[var(--accent)] px-3 py-2 text-sm font-medium text-[var(--accent-fg)] disabled:opacity-40"
          >
            Подключить
          </button>
        )}
      </header>
      {loadError && (
        <div className="mx-3 mt-3 rounded-xl bg-red-900/30 px-4 py-2.5 text-sm text-red-300">
          {loadError}
        </div>
      )}
      {info && !info.enabled && (
        <div className="m-4 rounded-2xl border border-[var(--border-subtle)] p-4 text-sm text-[var(--fg-secondary)]">
          Терминал выключен: на сервере не задан ключ шифрования.
        </div>
      )}
      {info && info.enabled && !info.configured && (
        <div className="m-4 rounded-2xl border border-[var(--border-subtle)] p-4 text-sm text-[var(--fg-secondary)]">
          Сначала добавьте SSH-ключ в настройках.
          <button
            type="button"
            onClick={onOpenSettings}
            className="ml-2 text-[var(--fg-primary)] underline"
          >
            Открыть настройки
          </button>
        </div>
      )}
      <div ref={hostRef} className="ssh-term min-h-0 flex-1 p-2" />
    </main>
  );
}
