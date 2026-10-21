import { Link, useParams } from "react-router-dom";
import OfficeProjectList from "@/components/office/OfficeProjectList";
import OfficeProjectView from "@/components/office/OfficeProjectView";

// Проектный офис: /office (список проектов) и /office/:id (проект с вкладками
// Паспорт, Бриф, Задание). Вкладки живут в components/office/<вкладка>/.
// Нечисловой id в адресе: «Проект не найден» без запроса к API.
function parseProjectId(id: string): number | null {
  return /^\d+$/.test(id) ? Number(id) : null;
}

export default function OfficePage() {
  const { id } = useParams();
  const projectId = id === undefined ? undefined : parseProjectId(id);
  return (
    <div className="min-h-dvh bg-[var(--bg-canvas)] text-[var(--fg-primary)]">
      <div className="mx-auto max-w-4xl p-4 sm:p-6">
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
    </div>
  );
}
