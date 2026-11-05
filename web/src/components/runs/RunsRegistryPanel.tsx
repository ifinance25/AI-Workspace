import { useMemo, useState } from "react";
import type { RunSummary } from "@/components/runs/runsApi";
import { STATUS_LABEL, type ReviewStatus } from "@/components/runs/runsLabels";
import { comparisonKindLabel, formatRunDate } from "@/components/runs/runsRegistryLabels";

const STATUS_ORDER: ReviewStatus[] = ["new", "needs_info", "confirmed", "rejected"];

function statusCells(stats: RunSummary["stats"]) {
  return STATUS_ORDER.map((key) => ({
    key,
    label: STATUS_LABEL[key],
    count: stats.by_status?.[key] ?? 0,
  }));
}

export default function RunsRegistryPanel({
  runs,
  activeRunId,
  onOpenRun,
}: {
  runs: RunSummary[];
  activeRunId: number | null;
  onOpenRun: (runId: number) => void;
}) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const sorted = useMemo(
    () =>
      [...runs].sort((a, b) => {
        const da = a.display_at ?? a.imported_at;
        const db = b.display_at ?? b.imported_at;
        return db.localeCompare(da);
      }),
    [runs],
  );

  if (runs.length === 0) {
    return (
      <p className="text-sm text-[var(--fg-secondary)]">В реестре пока нет загруженных прогонов.</p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border-subtle)]">
      <table className="w-full min-w-[720px] text-left text-sm" data-testid="runs-registry">
        <thead className="border-b border-[var(--border-subtle)] bg-[var(--bg-hover)] text-xs text-[var(--fg-secondary)]">
          <tr>
            <th className="px-3 py-2 font-medium">Дата</th>
            <th className="px-3 py-2 font-medium">Цель / сравнение</th>
            <th className="px-3 py-2 font-medium">Серия</th>
            <th className="px-3 py-2 font-medium">Документы</th>
            <th className="px-3 py-2 font-medium">Статусы</th>
            <th className="px-3 py-2 font-medium">Метрики</th>
            <th className="px-3 py-2 font-medium" />
          </tr>
        </thead>
        <tbody>
          {sorted.map((run) => {
            const isOpen = expanded === run.id;
            const cells = statusCells(run.stats);
            const maxCount = Math.max(1, ...cells.map((c) => c.count));
            return (
              <tr
                key={run.id}
                className={`border-b border-[var(--border-subtle)] ${
                  activeRunId === run.id ? "bg-[color-mix(in_srgb,var(--accent)_8%,transparent)]" : ""
                }`}
              >
                <td className="px-3 py-2 align-top whitespace-nowrap">
                  {formatRunDate(run.display_at ?? run.imported_at)}
                </td>
                <td className="px-3 py-2 align-top">
                  <div className="font-medium">{comparisonKindLabel(run.comparison_kind)}</div>
                  <div className="text-xs text-[var(--fg-secondary)]">{run.title || run.run_key}</div>
                </td>
                <td className="px-3 py-2 align-top whitespace-nowrap">
                  <span className="font-mono text-xs">{run.series_key}</span>
                  <span className="ml-1 rounded bg-[var(--bg-hover)] px-1.5 py-0.5 text-xs">
                    v{run.import_version}
                  </span>
                  {run.parent_run_id ? (
                    <div className="text-xs text-[var(--fg-secondary)]">← #{run.parent_run_id}</div>
                  ) : null}
                </td>
                <td className="px-3 py-2 align-top">
                  <button
                    type="button"
                    className="text-left text-xs text-[var(--accent)] underline"
                    onClick={() => setExpanded(isOpen ? null : run.id)}
                  >
                    {run.documents.length} док.
                  </button>
                  {isOpen ? (
                    <ul className="mt-1 list-inside list-disc text-xs text-[var(--fg-secondary)]">
                      {run.documents.map((doc, idx) => (
                        <li key={`${run.id}-${idx}`}>
                          {doc.role ? `${doc.role}: ` : ""}
                          {doc.name}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-0.5 line-clamp-1 text-xs text-[var(--fg-secondary)]">
                      {run.documents.map((d) => d.name).join(", ")}
                    </p>
                  )}
                </td>
                <td className="px-3 py-2 align-top">
                  <div className="flex flex-wrap gap-1">
                    {cells.map((cell) => (
                      <span
                        key={cell.key}
                        className="rounded bg-[var(--bg-hover)] px-1.5 py-0.5 text-xs"
                        title={cell.label}
                      >
                        {cell.count}
                      </span>
                    ))}
                  </div>
                  {isOpen ? (
                    <div className="mt-2 flex h-12 items-end gap-1" aria-hidden>
                      {cells.map((cell) => (
                        <div
                          key={cell.key}
                          className="w-3 rounded-t bg-[var(--accent-brand)] opacity-80"
                          style={{ height: `${(cell.count / maxCount) * 100}%`, minHeight: cell.count ? 4 : 0 }}
                          title={`${cell.label}: ${cell.count}`}
                        />
                      ))}
                    </div>
                  ) : null}
                </td>
                <td className="px-3 py-2 align-top text-xs">
                  <div>Разобрано: {run.stats.reviewed}</div>
                  <div>
                    Закрытие:{" "}
                    {run.stats.run_can_close ? (
                      <span className="text-green-700 dark:text-green-400">можно</span>
                    ) : (
                      <span>осталось {run.stats.pending_decision}</span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2 align-top">
                  <button
                    type="button"
                    className="rounded-lg bg-[var(--bg-hover)] px-2 py-1 text-xs"
                    onClick={() => onOpenRun(run.id)}
                  >
                    Открыть
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
