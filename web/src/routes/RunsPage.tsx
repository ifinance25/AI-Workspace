import { Link, useNavigate, useParams } from "react-router-dom";
import AppShell from "@/components/AppShell";
import RunsScreens from "@/components/runs/RunsScreens";

function parseProjectId(id: string): number | null {
  return /^\d+$/.test(id) ? Number(id) : null;
}

export default function RunsPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const projectId = id === undefined ? null : parseProjectId(id);

  return (
    <AppShell
      activeSessionUuid={null}
      openLastChat={false}
      onSelectSession={() => navigate("/")}
      mobileHeaderTitle="Прогоны"
    >
      <div className="mx-auto max-w-7xl p-4 text-[var(--fg-primary)] sm:p-6">
        {projectId === null ? (
          <p>Проект не найден</p>
        ) : (
          <RunsScreens
            projectId={projectId}
            runViewTopRow={(backButton) => (
              <div className="flex flex-wrap items-center justify-start gap-3">
                {backButton}
                <Link to={`/office/${projectId}/members`} className="underline">
                  Команда
                </Link>
              </div>
            )}
          />
        )}
      </div>
    </AppShell>
  );
}
