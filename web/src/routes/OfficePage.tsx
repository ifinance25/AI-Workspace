import { Link, useNavigate, useParams } from "react-router-dom";
import AppShell from "@/components/AppShell";
import OfficeProjectList from "@/components/office/OfficeProjectList";
import OfficeProjectView from "@/components/office/OfficeProjectView";
import type { Session } from "@/lib/types";

function parseProjectId(id: string): number | null {
  return /^\d+$/.test(id) ? Number(id) : null;
}

export default function OfficePage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const projectId = id === undefined ? undefined : parseProjectId(id);

  const onSelectSession = (s: Session | null) => {
    if (s) navigate("/");
    else navigate("/");
  };

  return (
    <AppShell
      activeSessionUuid={null}
      openLastChat={false}
      onSelectSession={onSelectSession}
      mobileHeaderTitle="Проектный офис"
    >
      <div className="mx-auto max-w-4xl p-4 text-[var(--fg-primary)] sm:p-6">
        {projectId === undefined && <OfficeProjectList />}
        {projectId === null && (
          <>
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
              <h1 className="text-xl font-semibold sm:text-2xl">Проект</h1>
              <Link
                to="/office"
                className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm"
              >
                ← К проектам
              </Link>
            </div>
            <div className="mb-3 rounded-xl bg-red-900/30 px-3 py-2 text-sm text-red-300">
              Проект не найден
            </div>
          </>
        )}
        {typeof projectId === "number" && <OfficeProjectView projectId={projectId} />}
      </div>
    </AppShell>
  );
}
