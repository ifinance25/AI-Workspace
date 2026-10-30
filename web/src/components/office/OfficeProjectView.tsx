import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "@/api/client";
import { officeApi, type OfficeProject } from "@/components/office/officeApi";
import BriefTab from "@/components/office/brief/BriefTab";
import PassportTab from "@/components/office/passport/PassportTab";
import SpecTab from "@/components/office/spec/SpecTab";

type TabId = "passport" | "brief" | "spec";

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "passport", label: "Паспорт" },
  { id: "brief", label: "Бриф" },
  { id: "spec", label: "Задание" },
];

// Страница проекта офиса (/office/:id): шапка и три вкладки. Содержимое
// вкладок живёт в components/office/<вкладка>/ и получает загруженный project.
export default function OfficeProjectView({ projectId }: { projectId: number }) {
  const nav = useNavigate();
  const [project, setProject] = useState<OfficeProject | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("passport");

  useEffect(() => {
    let alive = true;
    setProject(null);
    setError(null);
    officeApi.getProject(projectId).then(
      (p) => {
        if (alive) setProject(p);
      },
      (e: Error) => {
        if (!alive) return;
        setError(e instanceof ApiError && e.status === 404 ? "Проект не найден" : e.message);
      },
    );
    return () => {
      alive = false;
    };
  }, [projectId]);

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold sm:text-2xl">{project?.name ?? "Проект"}</h1>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => nav("/office")}
            className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm"
          >
            ← К проектам
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded-xl bg-red-900/30 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}
      {!project && !error && <p className="text-sm text-[var(--fg-muted)]">Загрузка…</p>}

      {project && (
        <>
          <div
            role="tablist"
            className="mb-6 flex gap-2 overflow-x-auto border-b border-[var(--border-subtle)]"
          >
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={`shrink-0 px-4 py-2 text-sm font-medium transition-colors ${
                  tab === t.id
                    ? "border-b-2 border-[var(--accent)] text-[var(--accent)]"
                    : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-sidebar)] p-3 sm:p-6"
          >
            {tab === "passport" && (
              <PassportTab project={project} onProjectChange={setProject} />
            )}
            {tab === "brief" && <BriefTab project={project} />}
            {tab === "spec" && <SpecTab project={project} />}
          </div>
        </>
      )}
    </>
  );
}
