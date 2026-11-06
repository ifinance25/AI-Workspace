import { useMemo } from "react";
import type { RunStats, RunSummary } from "@/components/runs/runsApi";
import { comparisonKindLabel, formatRunDate } from "@/components/runs/runsRegistryLabels";

function sumStats(runs: RunSummary[]): RunStats {
  const empty: RunStats = {
    total: 0,
    by_status: {},
    reviewed: 0,
    validated: 0,
    pending_decision: 0,
    run_can_close: true,
    findings_edits_done: 0,
    edits_total: 0,
    edits_applied: 0,
    llm_agreement: null,
    slices: { severity: [], doc: [], category: [] },
  };
  return runs.reduce((acc, r) => {
    const s = r.stats;
    const by = { ...acc.by_status };
    for (const [k, v] of Object.entries(s.by_status ?? {})) {
      const key = k as keyof typeof by;
      by[key] = (by[key] ?? 0) + (v ?? 0);
    }
    return {
      ...acc,
      total: acc.total + s.total,
      by_status: by,
      reviewed: acc.reviewed + (s.reviewed ?? s.validated ?? 0),
      validated: acc.validated + (s.validated ?? 0),
      pending_decision: acc.pending_decision + s.pending_decision,
      run_can_close: acc.run_can_close && s.run_can_close,
      findings_edits_done: acc.findings_edits_done + s.findings_edits_done,
      edits_total: acc.edits_total + s.edits_total,
      edits_applied: acc.edits_applied + s.edits_applied,
    };
  }, empty);
}

export default function RunsAggregateStatsPanel({
  runs,
  onOpenRun,
}: {
  runs: RunSummary[];
  onOpenRun?: (runId: number) => void;
}) {
  const groups = useMemo(() => {
    const map = new Map<string, RunSummary[]>();
    for (const run of runs) {
      const key = run.comparison_kind || "unknown";
      const bucket = map.get(key) ?? [];
      bucket.push(run);
      map.set(key, bucket);
    }
    return [...map.entries()]
      .map(([kind, items]) => ({
        kind,
        label: comparisonKindLabel(kind),
        runs: [...items].sort((a, b) => {
          const da = a.display_at ?? a.imported_at;
          const db = b.display_at ?? b.imported_at;
          return db.localeCompare(da);
        }),
        totals: sumStats(items),
      }))
      .sort((a, b) => a.label.localeCompare(b.label, "ru"));
  }, [runs]);

  if (runs.length === 0) {
    return (
      <p className="text-sm text-[var(--fg-secondary)]" data-testid="runs-aggregate-stats">
        Нет прогонов для сравнения.
      </p>
    );
  }

  return (
    <div className="space-y-8" data-testid="runs-aggregate-stats">
      <p className="text-sm text-[var(--fg-secondary)]">
        Сводка по типам сравнения: сколько прогонов загружено и суммарные метрики находок в каждой
        группе.
      </p>
      {groups.map((group) => {
        const t = group.totals;
        const reviewed = t.reviewed ?? t.validated;
        return (
          <section
            key={group.kind}
            className="rounded-xl border border-[var(--border-subtle)] p-4"
            data-testid={`stats-group-${group.kind}`}
          >
            <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold">{group.label}</h2>
                <p className="text-xs text-[var(--fg-secondary)]">
                  Прогонов: {group.runs.length} · тип: <code className="font-mono">{group.kind}</code>
                </p>
              </div>
              <div className="flex flex-wrap gap-3 text-sm">
                <span>
                  Находок: <b>{t.total}</b>
                </span>
                <span>
                  Разобрано: <b>{reviewed}</b>
                </span>
                <span>
                  Без решения: <b>{t.pending_decision}</b>
                </span>
                <span>
                  Можно закрыть все:{" "}
                  <b className={t.run_can_close ? "text-green-700 dark:text-green-400" : ""}>
                    {t.run_can_close ? "да" : "нет"}
                  </b>
                </span>
              </div>
            </header>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="border-b border-[var(--border-subtle)] text-xs text-[var(--fg-secondary)]">
                  <tr>
                    <th className="px-2 py-2 font-medium">Дата</th>
                    <th className="px-2 py-2 font-medium">Прогон</th>
                    <th className="px-2 py-2 font-medium">Находок</th>
                    <th className="px-2 py-2 font-medium">Разобрано</th>
                    <th className="px-2 py-2 font-medium">Без решения</th>
                    <th className="px-2 py-2 font-medium">Закрытие</th>
                    <th className="px-2 py-2 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {group.runs.map((run) => (
                    <tr key={run.id} className="border-b border-[var(--border-subtle)]">
                      <td className="px-2 py-2 whitespace-nowrap">
                        {formatRunDate(run.display_at ?? run.imported_at)}
                      </td>
                      <td className="px-2 py-2">
                        <div className="font-medium">{run.title || run.run_key}</div>
                        <div className="font-mono text-xs text-[var(--fg-secondary)]">{run.run_key}</div>
                      </td>
                      <td className="px-2 py-2">{run.stats.total}</td>
                      <td className="px-2 py-2">{run.stats.reviewed ?? run.stats.validated}</td>
                      <td className="px-2 py-2">{run.stats.pending_decision}</td>
                      <td className="px-2 py-2">
                        {run.stats.run_can_close ? (
                          <span className="text-green-700 dark:text-green-400">можно</span>
                        ) : (
                          "нет"
                        )}
                      </td>
                      <td className="px-2 py-2">
                        {onOpenRun ? (
                          <button
                            type="button"
                            className="rounded-lg bg-[var(--bg-hover)] px-2 py-1 text-xs"
                            onClick={() => onOpenRun(run.id)}
                          >
                            Открыть
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}
