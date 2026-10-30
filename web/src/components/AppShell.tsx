import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { PanelLeftIcon } from "@/components/icons";
import SettingsModal from "@/components/SettingsModal";
import Sidebar from "@/components/Sidebar";
import type { Session } from "@/lib/types";
import { NARROW_VIEWPORT, useMediaQuery } from "@/lib/useMediaQuery";

const COLLAPSED_KEY = "ai-workspace.sidebarCollapsed";

interface AppShellControls {
  openNav: () => void;
  openSettings: (tab?: "ssh") => void;
}

const AppShellControlsContext = createContext<AppShellControls>({
  openNav: () => {},
  openSettings: () => {},
});

export function useAppShellControls() {
  return useContext(AppShellControlsContext);
}

export interface AppShellProps {
  children: ReactNode;
  activeSessionUuid?: string | null;
  onSelectSession?: (s: Session | null) => void;
  showTerminal?: boolean;
  terminalActive?: boolean;
  onOpenTerminal?: () => void;
  mobileHeaderTitle?: string;
}

export default function AppShell({
  children,
  activeSessionUuid = null,
  onSelectSession = () => {},
  showTerminal = false,
  terminalActive = false,
  onOpenTerminal,
  mobileHeaderTitle,
}: AppShellProps) {
  const isNarrow = useMediaQuery(NARROW_VIEWPORT);
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

  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "1" : "0");
    } catch {
      /* localStorage может быть недоступен */
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

  const openSettings = (tab?: "ssh") => {
    setSettingsTab(tab);
    setSettingsOpen(true);
    if (isNarrow) setNavOpen(false);
  };

  const sidebar = (
    <Sidebar
      activeSessionUuid={activeSessionUuid}
      onSelectSession={(s) => {
        onSelectSession(s);
        if (isNarrow) setNavOpen(false);
      }}
      collapsed={isNarrow ? false : collapsed}
      overlay={isNarrow}
      onToggleCollapsed={() => {
        if (isNarrow) setNavOpen(false);
        else setCollapsed((v) => !v);
      }}
      onOpenSettings={() => openSettings()}
      onOpenTerminal={
        showTerminal && onOpenTerminal
          ? () => {
              onOpenTerminal();
              if (isNarrow) setNavOpen(false);
            }
          : undefined
      }
      terminalActive={terminalActive}
    />
  );

  return (
    <AppShellControlsContext.Provider
      value={{
        openNav: () => setNavOpen(true),
        openSettings: openSettings,
      }}
    >
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
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--bg-canvas)]">
        {isNarrow && mobileHeaderTitle && (
          <header className="flex shrink-0 items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2 lg:hidden">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              className="icon-btn flex h-11 w-11 items-center justify-center rounded-xl text-[var(--fg-secondary)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)]"
              aria-label="Открыть меню"
              title="Меню"
            >
              <PanelLeftIcon size={20} />
            </button>
            <span className="text-sm text-[var(--fg-secondary)]">{mobileHeaderTitle}</span>
          </header>
        )}
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
      <SettingsModal
        open={settingsOpen}
        initialTab={settingsTab}
        onClose={() => {
          setSettingsOpen(false);
          setSettingsTab(undefined);
        }}
      />
    </div>
    </AppShellControlsContext.Provider>
  );
}
