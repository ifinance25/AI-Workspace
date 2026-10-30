import { useParams } from "react-router-dom";
import RedmineScreens from "@/components/redmine/RedmineScreens";

function parseProjectId(id: string): number | null {
  return /^\d+$/.test(id) ? Number(id) : null;
}

export default function RedminePage() {
  const { id } = useParams();
  const projectId = id === undefined ? null : parseProjectId(id);
  return (
    <div className="min-h-dvh bg-[var(--bg-canvas)] text-[var(--fg-primary)]">
      <div className="mx-auto max-w-5xl p-4 sm:p-6">
        {projectId === null ? (
          <p>Проект не найден</p>
        ) : (
          <RedmineScreens projectId={projectId} />
        )}
      </div>
    </div>
  );
}
