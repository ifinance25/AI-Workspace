import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { officeApi, type OfficeProject } from "@/components/office/officeApi";
import NewProjectButton from "@/components/office/passport/NewProjectButton";

// Страница списка: просим на один больше, чтобы знать, есть ли ещё.
const PAGE = 20;

// Список проектов офиса (/office): только те, что открыты пользователю.
// Листается страницами по PAGE, кнопка «Показать ещё» догружает следующую.
export default function OfficeProjectList() {
  const nav = useNavigate();
  const [projects, setProjects] = useState<OfficeProject[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function loadPage(offset: number) {
    return officeApi.listProjects({ offset, limit: PAGE + 1 }).then((list) => {
      setHasMore(list.length > PAGE);
      setProjects((prev) => [...(offset ? prev ?? [] : []), ...list.slice(0, PAGE)]);
    });
  }

  useEffect(() => {
    let alive = true;
    officeApi.listProjects({ offset: 0, limit: PAGE + 1 }).then(
      (list) => {
        if (!alive) return;
        setHasMore(list.length > PAGE);
        setProjects(list.slice(0, PAGE));
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
      {hasMore && projects && (
        <button
          type="button"
          onClick={() => loadPage(projects.length).catch((e: Error) => setError(e.message))}
          className="mt-3 rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm"
        >
          Показать ещё
        </button>
      )}
    </>
  );
}
