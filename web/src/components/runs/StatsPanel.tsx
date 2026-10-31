// Статистика прогона. Цифры считает сервер, экран только показывает.
import type { RunStats, SliceRow } from "@/components/runs/runsApi";

function Tile({ value, label, tone = "" }: { value: number | string; label: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-sidebar)] p-4">
      <div className={`text-3xl font-semibold ${tone}`}>{value}</div>
      <div className="mt-1 text-sm text-[var(--fg-secondary)]">{label}</div>
    </div>
  );
}

function Slice({ title, rows }: { title: string; rows: SliceRow[] }) {
  return (
    <div className="overflow-x-auto">
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      <table className="w-full text-left text-sm">
        <thead className="text-[var(--fg-secondary)]">
          <tr>
            <th className="py-1 pr-3 font-normal">Значение</th>
            <th className="py-1 pr-3 font-normal">Находок</th>
            <th className="py-1 pr-3 font-normal">Валидация пройдена</th>
            <th className="py-1 font-normal">Правки внесены</th>
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
        </tbody>
      </table>
    </div>
  );
}

export default function StatsPanel({ stats }: { stats: RunStats }) {
  const percent = stats.total ? Math.round((stats.validated / stats.total) * 100) : 0;
  const fixedPercent = stats.total ? Math.round((stats.findings_edits_done / stats.total) * 100) : 0;
  const by = stats.by_status;
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
      <div className="grid gap-6 lg:grid-cols-3">
        <Slice title="По важности" rows={stats.slices.severity} />
        <Slice title="По документу" rows={stats.slices.doc} />
        <Slice title="По категории" rows={stats.slices.category} />
      </div>
    </div>
  );
}
