// Статистика прогона. Цифры считает сервер, экран только показывает.
import { useState } from "react";
import type { RunStats, SliceRow } from "@/components/runs/runsApi";

type SliceTab = "severity" | "doc" | "category";

function Tile({ value, label, tone = "" }: { value: number | string; label: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-sidebar)] p-4">
      <div className={`text-3xl font-semibold ${tone}`}>{value}</div>
      <div className="mt-1 text-sm text-[var(--fg-secondary)]">{label}</div>
    </div>
  );
}

function sumRows(rows: SliceRow[]) {
  return rows.reduce(
    (acc, row) => ({
      total: acc.total + row.total,
      validated: acc.validated + (row.validated ?? 0),
      fixed: acc.fixed + (row.fixed ?? 0),
    }),
    { total: 0, validated: 0, fixed: 0 },
  );
}

function SliceTable({ rows }: { rows: SliceRow[] }) {
  const totals = sumRows(rows);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-[var(--fg-secondary)]">
          <tr>
            <th className="py-1 pr-3 font-semibold">Значение</th>
            <th className="py-1 pr-3 font-semibold">Находок</th>
            <th className="py-1 pr-3 font-semibold">Валидация пройдена</th>
            <th className="py-1 font-semibold">Правки внесены</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-t border-[var(--border-subtle)]">
              <td className="py-1 pr-3">{row.label || "Не указано"}</td>
              <td className="py-1 pr-3">{row.total}</td>
              <td className="py-1 pr-3">{row.validated ?? 0}</td>
              <td className="py-1">{row.fixed ?? 0}</td>
            </tr>
          ))}
          <tr className="border-t border-[var(--border-subtle)] font-medium">
            <td className="py-1 pr-3">Итого</td>
            <td className="py-1 pr-3">{totals.total}</td>
            <td className="py-1 pr-3">{totals.validated}</td>
            <td className="py-1">{totals.fixed}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

const SLICE_TABS: Array<[SliceTab, string]> = [
  ["severity", "По важности"],
  ["doc", "По документу"],
  ["category", "По категории"],
];

export default function StatsPanel({ stats }: { stats: RunStats }) {
  const [sliceTab, setSliceTab] = useState<SliceTab>("severity");
  const percent = stats.total ? Math.round((stats.validated / stats.total) * 100) : 0;
  const fixedPercent = stats.total ? Math.round((stats.findings_edits_done / stats.total) * 100) : 0;
  const by = stats.by_status;
  const sliceRows = stats.slices[sliceTab];
  return (
    <div className="space-y-6" data-testid="stats-panel">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile value={stats.total} label="Всего находок" />
        <Tile
          value={stats.validated}
          label="Валидация пройдена"
          tone="text-[var(--status-success-fg)]"
        />
        <Tile
          value={stats.findings_edits_done}
          label="Правки внесены в документы"
          tone="text-[var(--status-success-fg)]"
        />
        <Tile value={by.new ?? 0} label="Не разобрано" />
        <Tile value={by.needs_info ?? 0} label="На уточнение" tone="text-[var(--accent-brand)]" />
        <Tile value={by.confirmed ?? 0} label="Подтверждено" />
        <Tile value={by.rejected ?? 0} label="Отклонено" tone="text-[var(--status-error-fg)]" />
        <Tile
          value={`${stats.edits_applied} из ${stats.edits_total}`}
          label="Правок внесено"
        />
      </div>
      <div className="space-y-3">
        <div>
          <div className="mb-1 flex justify-between text-sm">
            <span>Валидация пройдена</span>
            <span>{percent}%</span>
          </div>
          <div className="h-2 rounded bg-[var(--bg-hover)]">
            <div className="h-2 rounded bg-[var(--status-success-fg)]" style={{ width: `${percent}%` }} />
          </div>
        </div>
        <div>
          <div className="mb-1 flex justify-between text-sm">
            <span>Правки внесены в документы</span>
            <span>{fixedPercent}%</span>
          </div>
          <div className="h-2 rounded bg-[var(--bg-hover)]">
            <div className="h-2 rounded bg-[var(--status-success-fg)] opacity-60" style={{ width: `${fixedPercent}%` }} />
          </div>
        </div>
      </div>
      {stats.llm_agreement !== null && (
        <p className="text-sm text-[var(--fg-secondary)]">
          Подтверждено людьми из разобранных: {Math.round(stats.llm_agreement * 100)}%. Агенты
          признали все находки действительными, поэтому это доля совпадения вердикта агентов с
          решением человека.
        </p>
      )}
      <div>
        <div role="tablist" className="mb-3 flex flex-wrap gap-2 border-b border-[var(--border-subtle)]">
          {SLICE_TABS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={sliceTab === id}
              onClick={() => setSliceTab(id)}
              className={`px-3 py-2 text-sm font-medium ${
                sliceTab === id
                  ? "border-b-2 border-[var(--accent)] text-[var(--accent)]"
                  : "text-[var(--fg-secondary)]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <SliceTable rows={sliceRows} />
      </div>
    </div>
  );
}
