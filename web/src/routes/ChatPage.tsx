import { useState } from "react";
import AppShell, { useAppShellControls } from "@/components/AppShell";
import Chat from "@/components/Chat";
import TerminalPanel from "@/components/TerminalPanel";
import { useAuth } from "@/auth/AuthContext";
import { startNewSession } from "@/lib/newSession";
import type { Session } from "@/lib/types";

function ChatMain({
  active,
  setActive,
  view,
}: {
  active: Session | null;
  setActive: (s: Session | null) => void;
  view: "chat" | "terminal";
}) {
  const { openNav, openSettings } = useAppShellControls();

  if (view === "terminal") {
    return (
      <TerminalPanel
        onOpenSidebar={openNav}
        onOpenSettings={() => openSettings("ssh")}
      />
    );
  }
  if (active) {
    return (
      <Chat
        session={active}
        key={active.session_uuid}
        onOpenSidebar={openNav}
        onNewChat={() =>
          void startNewSession(
            { path: active.project_path, name: active.project_name },
            setActive,
          )
        }
      />
    );
  }
  return (
    <main className="flex min-h-full min-w-0 flex-1 flex-col bg-[var(--bg-canvas)]">
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
  );
}

export default function ChatPage() {
  const [active, setActive] = useState<Session | null>(null);
  const { user } = useAuth();
  const isAdmin = Boolean(user?.is_admin);
  const [view, setView] = useState<"chat" | "terminal">("chat");

  const selectSession = (s: Session | null) => {
    setActive(s);
    setView("chat");
  };

  return (
    <AppShell
      activeSessionUuid={active?.session_uuid ?? null}
      onSelectSession={selectSession}
      showTerminal={isAdmin}
      terminalActive={view === "terminal"}
      onOpenTerminal={() => setView("terminal")}
      mobileHeaderTitle={view === "terminal" ? "Терминал" : "Чаты"}
    >
      <ChatMain active={active} setActive={setActive} view={isAdmin ? view : "chat"} />
    </AppShell>
  );
}
