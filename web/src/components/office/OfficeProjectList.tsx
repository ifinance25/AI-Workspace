import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { officeApi, type OfficeProject } from "@/components/office/officeApi";
import NewProjectButton from "@/components/office/passport/NewProjectButton";

// Список проектов офиса (/office): только те, что открыты пользователю.
export default function OfficeProjectList() {
  const nav = useNavigate();
  const [projects, setProjects] = useState<OfficeProject[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    officeApi.listProjects().then(
      (list) => {
        if (alive) setProjects(list);
      },
      (e: Error) => {
        if (alive) setError(e.message);
      },
    );
    return () => {
      alive = false;
    };
  }, []);

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold sm:text-2xl">Проектный офис</h1>
        <div className="flex items-center gap-2">
          <NewProjectButton onCreated={(id) => nav(`/office/${id}`)} />
          <button
            onClick={() => nav("/")}
            className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm"
          >
            ← В чат
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded-xl bg-red-900/30 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}
      {projects === null && !error && (
        <p className="text-sm text-[var(--fg-muted)]">Загрузка…</p>
      )}
      {projects !== null && projects.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">Проектов нет</p>
      )}
      {projects !== null && projects.length > 0 && (
        <ul className="divide-y divide-[var(--border-subtle)] rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-sidebar)]">
          {projects.map((p) => (
            <li key={p.id}>
              <Link
                to={`/office/${p.id}`}
                className="block px-4 py-3 font-medium hover:bg-[var(--bg-hover)]"
              >
                {p.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
