import { useNavigate, useParams } from "react-router-dom";
import AppShell from "@/components/AppShell";
import RedmineScreens from "@/components/redmine/RedmineScreens";
import type { Session } from "@/lib/types";

function parseProjectId(id: string): number | null {
  return /^\d+$/.test(id) ? Number(id) : null;
}

export default function RedminePage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const projectId = id === undefined ? null : parseProjectId(id);

  const onSelectSession = (s: Session | null) => {
    if (s) navigate("/");
    else navigate("/");
  };

  return (
    <AppShell
      activeSessionUuid={null}
      onSelectSession={onSelectSession}
      mobileHeaderTitle="Задачи"
    >
      <div className="mx-auto max-w-5xl p-4 text-[var(--fg-primary)] sm:p-6">
        {projectId === null ? (
          <p>Проект не найден</p>
        ) : (
          <RedmineScreens projectId={projectId} />
        )}
      </div>
    </AppShell>
  );
}
