import { useEffect, useState } from "react";
import Chat from "@/components/Chat";
import { PanelLeftIcon } from "@/components/icons";
import SettingsModal from "@/components/SettingsModal";
import Sidebar from "@/components/Sidebar";
import TerminalPanel from "@/components/TerminalPanel";
import { startNewSession } from "@/lib/newSession";
import type { Session } from "@/lib/types";
import { NARROW_VIEWPORT, useMediaQuery } from "@/lib/useMediaQuery";

const COLLAPSED_KEY = "vels.sidebarCollapsed";

export default function ChatPage() {
  const isNarrow = useMediaQuery(NARROW_VIEWPORT);
  const [active, setActive] = useState<Session | null>(null);
  // Persist collapsed state across reloads — иначе юзер каждый раз
  // открывает страницу с collapsed=false и не понимает почему его
  // настройка не сохранилась.
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [navOpen, setNavOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<"ssh" | undefined>();
  const [view, setView] = useState<"chat" | "terminal">("chat");

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      /* localStorage может быть недоступен — игнорируем */
    }
  }, [collapsed]);

  useEffect(() => {
    if (!isNarrow) setNavOpen(false);
  }, [isNarrow]);

  useEffect(() => {
    if (!isNarrow || !navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [isNarrow, navOpen]);

  const selectSession = (s: Session | null) => {
    setActive(s);
    setView("chat");
    if (isNarrow) setNavOpen(false);
  };

  const openSettings = (tab?: "ssh") => {
    setSettingsTab(tab);
    setSettingsOpen(true);
    if (isNarrow) setNavOpen(false);
  };

  const sidebar = (
    <Sidebar
      activeSessionUuid={active?.session_uuid ?? null}
      onSelectSession={selectSession}
      collapsed={isNarrow ? false : collapsed}
      overlay={isNarrow}
      onToggleCollapsed={() => {
        if (isNarrow) setNavOpen(false);
        else setCollapsed((v) => !v);
      }}
      onOpenSettings={() => openSettings()}
      onOpenTerminal={() => {
        setView("terminal");
        if (isNarrow) setNavOpen(false);
      }}
      terminalActive={view === "terminal"}
    />
  );

  return (
    <div className="flex h-dvh max-h-dvh overflow-hidden">
      {isNarrow ? (
        <>
          {navOpen && (
            <button
              type="button"
              className="fixed inset-0 z-40 bg-black/50"
              aria-label="Закрыть список чатов"
              onClick={() => setNavOpen(false)}
            />
          )}
          <div
            className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-200 ease-out ${
              navOpen ? "translate-x-0" : "-translate-x-full"
            }`}
          >
            {sidebar}
          </div>
        </>
      ) : (
        sidebar
      )}
      {view === "terminal" ? (
        <TerminalPanel
          onOpenSidebar={() => setNavOpen(true)}
          onOpenSettings={() => openSettings("ssh")}
        />
      ) : active ? (
        <Chat
          session={active}
          key={active.session_uuid}
          onOpenSidebar={() => setNavOpen(true)}
          onNewChat={() =>
            void startNewSession(
              { path: active.project_path, name: active.project_name },
              setActive,
            )
          }
        />
      ) : (
        <main className="flex min-w-0 flex-1 flex-col bg-[var(--bg-canvas)]">
          <header className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2 lg:hidden">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              className="icon-btn flex h-11 w-11 items-center justify-center rounded-xl text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
              aria-label="Открыть список чатов"
              title="Чаты"
            >
              <PanelLeftIcon size={20} />
            </button>
            <span className="text-sm text-[var(--fg-secondary)]">Чаты</span>
          </header>
          <div className="flex flex-1 items-center justify-center px-4 sm:px-6">
            <div className="text-center">
              <div className="text-xl font-semibold text-[var(--fg-primary)]">
                Выберите чат или создайте новый
              </div>
              <div className="mt-2 text-base text-[var(--fg-muted)]">
                Откройте сессию слева — или нажмите <strong>Новый чат</strong>.
              </div>
            </div>
          </div>
        </main>
      )}

      <SettingsModal
        open={settingsOpen}
        initialTab={settingsTab}
        onClose={() => {
          setSettingsOpen(false);
          setSettingsTab(undefined);
        }}
      />
    </div>
  );
}
