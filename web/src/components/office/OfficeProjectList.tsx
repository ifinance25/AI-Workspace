import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { officeApi, type OfficeProject } from "@/components/office/officeApi";
import NewProjectButton from "@/components/office/passport/NewProjectButton";

// Страница списка: просим на один больше, чтобы знать, есть ли ещё.
const PAGE = 20;

const btnSecondary =
  "rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-2.5 py-1 text-sm text-[var(--fg-primary)] hover:bg-[var(--bg-hover)]";

// Список проектов офиса (/office): только те, что открыты пользователю.
// Листается страницами по PAGE, кнопка «Показать ещё» догружает следующую.
export default function OfficeProjectList() {
  const nav = useNavigate();
  const [projects, setProjects] = useState<OfficeProject[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

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

  function startEdit(project: OfficeProject) {
    setConfirmDeleteId(null);
    setEditId(project.id);
    setEditName(project.name);
  }

  function cancelEdit() {
    setEditId(null);
    setEditName("");
  }

  async function saveEdit(id: number) {
    const name = editName.trim();
    if (!name) {
      setError("Укажите название проекта");
      return;
    }
    setBusyId(id);
    setError(null);
    try {
      const updated = await officeApi.updateProject(id, { name });
      setProjects((prev) =>
        prev?.map((item) => (item.id === id ? { ...item, name: updated.name } : item)) ?? prev,
      );
      cancelEdit();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function remove(id: number) {
    setConfirmDeleteId(null);
    setBusyId(id);
    setError(null);
    try {
      await officeApi.deleteProject(id);
      setProjects((prev) => prev?.filter((item) => item.id !== id) ?? prev);
      if (editId === id) cancelEdit();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold sm:text-2xl">Проектный офис</h1>
        <div className="flex items-center gap-2">
          <NewProjectButton onCreated={(id) => nav(`/office/${id}`)} />
          <button
            type="button"
            onClick={() => nav("/")}
            className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm"
          >
            ← В чат
          </button>
        </div>
      </div>

      {error && <div className="alert-error mb-3">{error}</div>}
      {projects === null && !error && (
        <p className="text-sm text-[var(--fg-muted)]">Загрузка…</p>
      )}
      {projects !== null && projects.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">Проектов нет</p>
      )}
      {projects !== null && projects.length > 0 && (
        <ul className="divide-y divide-[var(--border-subtle)] rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-sidebar)]">
          {projects.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-2 px-3 py-2 sm:px-4 sm:py-3">
              {editId === p.id ? (
                <>
                  <input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    className="min-w-0 flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-3 py-1.5 text-sm"
                    autoFocus
                    aria-label="Название проекта"
                  />
                  <button
                    type="button"
                    className={btnSecondary}
                    disabled={busyId === p.id}
                    onClick={() => void saveEdit(p.id)}
                  >
                    Сохранить
                  </button>
                  <button type="button" className={btnSecondary} onClick={cancelEdit}>
                    Отмена
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to={`/office/${p.id}`}
                    className="min-w-0 flex-1 font-medium text-[var(--fg-primary)] hover:text-[var(--accent-brand)]"
                  >
                    {p.name}
                  </Link>
                  <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                    <Link to={`/office/${p.id}`} className={btnSecondary}>
                      Открыть
                    </Link>
                    <button type="button" className={btnSecondary} onClick={() => startEdit(p)}>
                      Переименовать
                    </button>
                    {confirmDeleteId === p.id ? (
                      <>
                        <span className="text-xs text-[var(--fg-secondary)]">Удалить?</span>
                        <button
                          type="button"
                          className="rounded-lg bg-[var(--status-error-bg)] px-2.5 py-1 text-sm text-[var(--status-error-fg)] border border-[var(--status-error-border)]"
                          disabled={busyId === p.id}
                          onClick={() => void remove(p.id)}
                        >
                          Да
                        </button>
                        <button
                          type="button"
                          className={btnSecondary}
                          onClick={() => setConfirmDeleteId(null)}
                        >
                          Нет
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className={btnSecondary}
                        onClick={() => {
                          setEditId(null);
                          setConfirmDeleteId(p.id);
                        }}
                      >
                        Удалить
                      </button>
                    )}
                  </div>
                </>
              )}
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
