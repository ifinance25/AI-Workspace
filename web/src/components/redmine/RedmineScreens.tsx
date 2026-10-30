// Четыре экрана зеркала и карточка задачи. Стили те же, что у офиса.
// Ключ API на страницу не выводится. Вики, настройки Redmine и учёт часов не входят.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";
import {
  redmineApi,
  type RedmineIssue,
  type RedminePerson,
  type RedmineView,
} from "@/components/redmine/redmineApi";

type ViewId = "board" | "list" | "analytics" | "forecasts";

const VIEWS: Array<{ id: ViewId; label: string }> = [
  { id: "board", label: "Доска" },
  { id: "list", label: "Список" },
  { id: "analytics", label: "Аналитика" },
  { id: "forecasts", label: "Прогнозы" },
];

const NOT_CONNECTED = "Redmine ещё не подключён";
const UNSET = "Не указан";

interface Draft {
  subject: string;
  description: string;
  statusId: string;
  assigneeId: string;
  start: string;
  due: string;
  notes: string;
}

function errorText(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  const json = message.indexOf("{");
  if (json >= 0) {
    try {
      const detail = (JSON.parse(message.slice(json)) as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
    } catch {
      // Ответ без JSON: показываем текст как есть.
    }
  }
  return message;
}

function personName(person: RedminePerson | null, empty: string): string {
  const name = person?.name?.trim();
  return name || empty;
}

function issueType(issue: RedmineIssue): string {
  return issue.type?.trim() || UNSET;
}

function issueEnvironment(issue: RedmineIssue): string {
  return issue.environment?.trim() || UNSET;
}

function statusName(issue: RedmineIssue): string {
  return issue.status?.name?.trim() || "Без статуса";
}

function parseStamp(value: string): number {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return Date.parse(`${value}T12:00:00Z`);
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? NaN : parsed;
}

function issueWhen(issue: RedmineIssue): number | null {
  const stamps = [
    issue.due_date,
    issue.start_date,
    ...issue.status_history.map((row) => row.at),
    ...issue.comments.map((row) => row.at),
  ].filter((value): value is string => Boolean(value));
  const times = stamps.map(parseStamp).filter((value) => !Number.isNaN(value));
  return times.length ? Math.max(...times) : null;
}

function inPeriod(when: number | null, period: string, now: number): boolean {
  if (period === "all") return true;
  if (when === null) return false;
  const day = 24 * 60 * 60 * 1000;
  if (period === "yesterday") {
    const start = Date.UTC(
      new Date(now).getUTCFullYear(),
      new Date(now).getUTCMonth(),
      new Date(now).getUTCDate(),
    );
    return when >= start - day && when < start;
  }
  const days = Number(period);
  if (!Number.isFinite(days)) return true;
  return when >= now - days * day;
}

function percentile(values: number[], q: number): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  const raw = lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  return Math.round(raw * 100) / 100;
}

function hoursText(value: number | null): string {
  return value === null ? "-" : String(value);
}

function unique(values: string[]): string[] {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b, "ru"));
}

function draftFrom(issue: RedmineIssue): Draft {
  return {
    subject: issue.subject,
    description: issue.description,
    statusId: issue.status?.id ?? "",
    assigneeId: issue.assignee?.user_id != null ? String(issue.assignee.user_id) : "",
    start: issue.start_date ?? "",
    due: issue.due_date ?? "",
    notes: "",
  };
}

function requestKey(): string {
  const uuid = globalThis.crypto?.randomUUID?.();
  return uuid || String(Date.now());
}

function emptyDraft(): Draft {
  return {
    subject: "",
    description: "",
    statusId: "",
    assigneeId: "",
    start: "",
    due: "",
    notes: "",
  };
}

const CREATE_STUB: RedmineIssue = {
  id: 0,
  subject: "",
  description: "",
  status: { id: "1", name: "Новая" },
  author: null,
  assignee: null,
  start_date: null,
  due_date: null,
  comments: [],
  status_history: [],
  assignee_history: [],
  ftt_section: "",
  cycle_hours: null,
};

export default function RedmineScreens({ projectId }: { projectId: number }) {
  const [view, setView] = useState<RedmineView | null>(null);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [screen, setScreen] = useState<ViewId>("board");
  const [open, setOpen] = useState<RedmineIssue | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createDraft, setCreateDraft] = useState<Draft | null>(null);
  const [filters, setFilters] = useState({
    type: "",
    environment: "",
    section: "",
    status: "",
    author: "",
    assignee: "",
    period: "all",
  });

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setForbidden(null);
    setError(null);
    setView(null);
    setOpen(null);
    redmineApi.loadProject(projectId, "").then(
      (loaded) => {
        if (!alive) return;
        setView(loaded);
        setLoading(false);
      },
      (err: unknown) => {
        if (!alive) return;
        if (err instanceof ApiError && err.status === 403) setForbidden(errorText(err));
        else setError(errorText(err));
        setLoading(false);
      },
    );
    return () => {
      alive = false;
    };
  }, [projectId]);

  const issues = view?.issues ?? [];
  const filtered = useMemo(() => {
    const now = Date.now();
    return issues.filter((issue) => {
      if (filters.type && issueType(issue) !== filters.type) return false;
      if (filters.environment && issueEnvironment(issue) !== filters.environment) return false;
      if (filters.section && issue.ftt_section !== filters.section) return false;
      if (filters.status && statusName(issue) !== filters.status) return false;
      if (filters.author && personName(issue.author, "Без автора") !== filters.author) return false;
      if (filters.assignee && personName(issue.assignee, "Не назначен") !== filters.assignee) {
        return false;
      }
      return inPeriod(issueWhen(issue), filters.period, now);
    });
  }, [issues, filters]);

  function remember(issue: RedmineIssue) {
    setView((current) => {
      if (!current) return current;
      const rest = current.issues.filter((item) => item.id !== issue.id);
      const message = current.message === NOT_CONNECTED ? "" : current.message;
      return { ...current, connected: true, message, issues: [...rest, issue] };
    });
    setOpen(issue);
    setDraft(draftFrom(issue));
  }

  async function submitCreate() {
    if (!createDraft) return;
    if (!createDraft.subject.trim()) {
      setError("Укажите тему задачи");
      return;
    }
    setBusy(true);
    setError(null);
    const body: Parameters<typeof redmineApi.createIssue>[1] = {
      request_key: requestKey(),
      redmine_project: "",
      subject: createDraft.subject.trim(),
      description: createDraft.description,
      start_date: createDraft.start || null,
      due_date: createDraft.due || null,
    };
    if (createDraft.statusId) body.status_id = createDraft.statusId;
    if (/^\d+$/.test(createDraft.assigneeId)) {
      body.assigned_to_id = Number(createDraft.assigneeId);
    }
    if (createDraft.notes.trim()) body.notes = createDraft.notes.trim();
    try {
      const result = await redmineApi.createIssue(projectId, body);
      setCreateOpen(false);
      setCreateDraft(null);
      remember(result.issue);
    } catch (err) {
      setError(errorText(err) || "Сохранение не удалось");
    } finally {
      setBusy(false);
    }
  }

  function openCreateModal() {
    setError(null);
    setCreateDraft(emptyDraft());
    setCreateOpen(true);
  }

  async function saveCard() {
    if (!open || !draft) return;
    setBusy(true);
    setError(null);
    const body: {
      subject: string;
      description: string;
      status_id?: string;
      assigned_to_id?: number;
      start_date: string | null;
      due_date: string | null;
      notes?: string;
    } = {
      subject: draft.subject,
      description: draft.description,
      start_date: draft.start || null,
      due_date: draft.due || null,
    };
    if (draft.statusId) body.status_id = draft.statusId;
    if (/^\d+$/.test(draft.assigneeId)) body.assigned_to_id = Number(draft.assigneeId);
    if (draft.notes.trim()) body.notes = draft.notes.trim();
    try {
      const result = await redmineApi.updateIssue(projectId, open.id, body);
      remember(result.issue);
    } catch (err) {
      setError(errorText(err) || "Сохранение не удалось");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <p className="text-sm text-[var(--fg-muted)]">Загрузка…</p>;

  if (forbidden) {
    return (
      <>
        <Header projectId={projectId} />
        <p role="alert" className="text-sm text-[var(--fg-primary)]">{forbidden}</p>
      </>
    );
  }

  const connected = Boolean(view?.connected);
  const banner = view?.message || (connected ? "" : NOT_CONNECTED);

  return (
    <>
      <Header projectId={projectId} />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold sm:text-2xl">Задачи</h1>
        <button
          type="button"
          onClick={openCreateModal}
          disabled={busy}
          className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-sm text-[var(--accent-fg)] hover:opacity-90 disabled:opacity-50"
        >
          Создать задачу
        </button>
      </div>
      {banner && (
        <p role="status" className="mb-4 text-sm text-[var(--fg-secondary)]">{banner}</p>
      )}
      {error && (
        <p role="alert" className="mb-4 text-sm text-red-600 dark:text-red-400">{error}</p>
      )}
      {connected && (
        <Filters
          issues={issues}
          filters={filters}
          onChange={(key, value) => setFilters((current) => ({ ...current, [key]: value }))}
        />
      )}
      <div
        role="tablist"
        className="mb-6 flex gap-2 overflow-x-auto border-b border-[var(--border-subtle)]"
      >
        {VIEWS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={screen === item.id}
            onClick={() => {
              setScreen(item.id);
              setOpen(null);
              setCreateOpen(false);
            }}
            className={`shrink-0 px-4 py-2 text-sm font-medium transition-colors ${
              screen === item.id
                ? "border-b-2 border-[var(--accent)] text-[var(--accent)]"
                : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-sidebar)] p-3 sm:p-6"
      >
        {open && draft ? (
          <IssueCard
            issue={open}
            draft={draft}
            people={peopleOptions(issues)}
            statuses={statusOptions(issues)}
            busy={busy}
            onChange={setDraft}
            onClose={() => setOpen(null)}
            onSave={() => void saveCard()}
          />
        ) : connected ? (
          <ScreenBody
            view={screen}
            issues={filtered}
            all={filtered}
            onOpen={(issue) => {
              setOpen(issue);
              setDraft(draftFrom(issue));
            }}
          />
        ) : null}
      </div>
      {createOpen && createDraft && (
        <div
          role="dialog"
          aria-label="Новая задача"
          className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 sm:items-center"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setCreateOpen(false);
              setCreateDraft(null);
            }
          }}
        >
          <div className="w-full max-w-2xl rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-sidebar)] p-4 sm:p-6">
            <IssueCard
              issue={CREATE_STUB}
              draft={createDraft}
              people={peopleOptions(issues)}
              statuses={statusOptions(issues)}
              busy={busy}
              creating
              onChange={setCreateDraft}
              onClose={() => {
                setCreateOpen(false);
                setCreateDraft(null);
              }}
              onSave={() => void submitCreate()}
            />
          </div>
        </div>
      )}
    </>
  );
}

function Header({ projectId }: { projectId: number }) {
  return (
    <div className="mb-4">
      <Link to={`/office/${projectId}`} className="text-sm text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]">
        ← К проекту
      </Link>
    </div>
  );
}

function Filters({
  issues,
  filters,
  onChange,
}: {
  issues: RedmineIssue[];
  filters: {
    type: string;
    environment: string;
    section: string;
    status: string;
    author: string;
    assignee: string;
    period: string;
  };
  onChange: (key: string, value: string) => void;
}) {
  const fields: Array<[string, string, string[]]> = [
    ["type", "Тип", unique(issues.map(issueType))],
    ["environment", "Окружение", unique(issues.map(issueEnvironment))],
    ["section", "Раздел функциональных требований", unique(issues.map((issue) => issue.ftt_section || UNSET))],
    ["status", "Статус", unique(issues.map(statusName))],
    ["author", "Автор", unique(issues.map((issue) => personName(issue.author, "Без автора")))],
    ["assignee", "Исполнитель", unique(issues.map((issue) => personName(issue.assignee, "Не назначен")))],
  ];
  return (
    <div className="mb-4 flex flex-wrap gap-3">
      {fields.map(([key, label, values]) => (
        <label key={key} className="flex min-w-40 flex-col gap-1 text-xs text-[var(--fg-secondary)]">
          {label}
          <select
            value={filters[key as keyof typeof filters]}
            onChange={(event) => onChange(key, event.target.value)}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 py-1.5 text-sm text-[var(--fg-primary)]"
          >
            <option value="">Все</option>
            {values.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
        </label>
      ))}
      <label className="flex min-w-40 flex-col gap-1 text-xs text-[var(--fg-secondary)]">
        Период
        <select
          value={filters.period}
          onChange={(event) => onChange("period", event.target.value)}
          className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 py-1.5 text-sm text-[var(--fg-primary)]"
        >
          <option value="all">Вся история</option>
          <option value="yesterday">Вчера</option>
          <option value="7">7 дней</option>
          <option value="30">30 дней</option>
          <option value="90">90 дней</option>
        </select>
      </label>
    </div>
  );
}

function ScreenBody({
  view,
  issues,
  all,
  onOpen,
}: {
  view: ViewId;
  issues: RedmineIssue[];
  all: RedmineIssue[];
  onOpen: (issue: RedmineIssue) => void;
}) {
  if (view === "board") return <Board issues={issues} onOpen={onOpen} />;
  if (view === "list") return <IssueList issues={issues} onOpen={onOpen} />;
  if (view === "analytics") return <Analytics issues={issues} />;
  return <Forecasts issues={issues} sample={all} onOpen={onOpen} />;
}

function Board({ issues, onOpen }: { issues: RedmineIssue[]; onOpen: (issue: RedmineIssue) => void }) {
  const columns = new Map<string, RedmineIssue[]>();
  for (const issue of issues) {
    const name = statusName(issue);
    columns.set(name, [...(columns.get(name) ?? []), issue]);
  }
  if (!issues.length) return <p className="text-sm text-[var(--fg-muted)]">Задач нет</p>;
  return (
    <div className="flex gap-3 overflow-x-auto">
      {[...columns.entries()].map(([name, cards]) => (
        <section key={name} aria-label={name} className="min-w-56 flex-1">
          <h2 className="mb-2 text-sm font-medium text-[var(--fg-primary)]">{name} · {cards.length}</h2>
          <ul className="space-y-2">
            {cards.map((issue) => (
              <li key={issue.id}>
                <button
                  type="button"
                  onClick={() => onOpen(issue)}
                  className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-3 py-2 text-left hover:bg-[var(--bg-hover)]"
                >
                  <span className="text-xs text-[var(--fg-muted)]">#{issue.id}</span>
                  <span className="mt-1 block text-sm text-[var(--fg-primary)]">{issue.subject}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function IssueList({ issues, onOpen }: { issues: RedmineIssue[]; onOpen: (issue: RedmineIssue) => void }) {
  if (!issues.length) return <p className="text-sm text-[var(--fg-muted)]">Задач нет</p>;
  return (
    <table className="w-full text-left text-sm">
      <thead className="text-[var(--fg-muted)]">
        <tr>
          <th className="py-2 pr-3 font-medium">Номер</th>
          <th className="py-2 pr-3 font-medium">Задача</th>
          <th className="py-2 pr-3 font-medium">Статус</th>
          <th className="py-2 pr-3 font-medium">Автор</th>
          <th className="py-2 font-medium">Исполнитель</th>
        </tr>
      </thead>
      <tbody>
        {issues.map((issue) => (
          <tr key={issue.id} className="border-t border-[var(--border-subtle)]">
            <td className="py-2 pr-3">#{issue.id}</td>
            <td className="py-2 pr-3">
              <button type="button" onClick={() => onOpen(issue)} className="text-left text-[var(--accent)]">
                {issue.subject}
              </button>
            </td>
            <td className="py-2 pr-3">{statusName(issue)}</td>
            <td className="py-2 pr-3">{personName(issue.author, "Без автора")}</td>
            <td className="py-2">{personName(issue.assignee, "Не назначен")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Analytics({ issues }: { issues: RedmineIssue[] }) {
  const rows = new Map<string, { count: number; hours: number[] }>();
  for (const issue of issues) {
    const name = personName(issue.assignee, "Не назначен");
    const row = rows.get(name) ?? { count: 0, hours: [] };
    row.count += 1;
    if (issue.cycle_hours != null) row.hours.push(issue.cycle_hours);
    rows.set(name, row);
  }
  const list = [...rows.entries()].sort((a, b) => b[1].count - a[1].count || a[0].localeCompare(b[0], "ru"));
  return (
    <>
      <h2 className="mb-3 text-sm font-medium text-[var(--fg-primary)]">Разрез по исполнителям</h2>
      {!list.length ? (
        <p className="text-sm text-[var(--fg-muted)]">Задач нет</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-[var(--fg-muted)]">
            <tr>
              <th className="py-2 pr-3 font-medium">Исполнитель</th>
              <th className="py-2 pr-3 font-medium">Задач</th>
              <th className="py-2 font-medium">Медиана, ч</th>
            </tr>
          </thead>
          <tbody>
            {list.map(([name, row]) => (
              <tr key={name} className="border-t border-[var(--border-subtle)]">
                <td className="py-2 pr-3">{name}</td>
                <td className="py-2 pr-3">{row.count}</td>
                <td className="py-2">{hoursText(percentile(row.hours, 0.5))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function Forecasts({
  issues,
  sample,
  onOpen,
}: {
  issues: RedmineIssue[];
  sample: RedmineIssue[];
  onOpen: (issue: RedmineIssue) => void;
}) {
  const openIssues = issues.filter((issue) => issue.cycle_hours == null);
  const hoursOf = (section?: string) => sample
    .filter((issue) => issue.cycle_hours != null && (section === undefined || issue.ftt_section === section))
    .map((issue) => issue.cycle_hours as number);
  return (
    <>
      <h2 className="mb-3 text-sm font-medium text-[var(--fg-primary)]">Прогноз открытых задач</h2>
      {!openIssues.length ? (
        <p className="text-sm text-[var(--fg-muted)]">Открытых задач нет</p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-[var(--fg-muted)]">
            <tr>
              <th className="py-2 pr-3 font-medium">Задача</th>
              <th className="py-2 pr-3 font-medium">Статус</th>
              <th className="py-2 pr-3 font-medium">Срок</th>
              <th className="py-2 font-medium">Ориентир, ч</th>
            </tr>
          </thead>
          <tbody>
            {openIssues.map((issue) => {
              const same = hoursOf(issue.ftt_section);
              const guide = percentile(same.length ? same : hoursOf(), 0.85);
              return (
                <tr key={issue.id} className="border-t border-[var(--border-subtle)]">
                  <td className="py-2 pr-3">
                    <button type="button" onClick={() => onOpen(issue)} className="text-left text-[var(--accent)]">
                      {issue.subject}
                    </button>
                  </td>
                  <td className="py-2 pr-3">{statusName(issue)}</td>
                  <td className="py-2 pr-3">{issue.due_date || "-"}</td>
                  <td className="py-2">{hoursText(guide)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </>
  );
}

function peopleOptions(issues: RedmineIssue[]): Array<{ value: string; label: string }> {
  const map = new Map<string, string>();
  for (const issue of issues) {
    for (const person of [issue.author, issue.assignee]) {
      if (!person?.name) continue;
      const value = person.user_id != null ? String(person.user_id) : `name:${person.name}`;
      map.set(value, person.name);
    }
  }
  return [...map.entries()].map(([value, label]) => ({ value, label }));
}

function statusOptions(issues: RedmineIssue[]): Array<{ value: string; label: string }> {
  const map = new Map<string, string>();
  for (const issue of issues) {
    if (issue.status?.id) map.set(issue.status.id, issue.status.name || issue.status.id);
  }
  return [...map.entries()].map(([value, label]) => ({ value, label }));
}

function IssueCard({
  issue,
  draft,
  people,
  statuses,
  busy,
  creating = false,
  onChange,
  onClose,
  onSave,
}: {
  issue: RedmineIssue;
  draft: Draft;
  people: Array<{ value: string; label: string }>;
  statuses: Array<{ value: string; label: string }>;
  busy: boolean;
  creating?: boolean;
  onChange: (draft: Draft) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  const field = "rounded-md border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 py-1.5 text-sm text-[var(--fg-primary)]";
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        onSave();
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-medium text-[var(--fg-primary)]">
          {creating ? "Новая задача" : `#${issue.id}`}
        </h2>
        <button type="button" onClick={onClose} className="text-sm text-[var(--fg-secondary)]">
          {creating ? "Отмена" : "Закрыть карточку"}
        </button>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        Тема
        <input
          value={draft.subject}
          onChange={(event) => onChange({ ...draft, subject: event.target.value })}
          className={field}
          autoFocus={creating}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Статус
        <select
          value={draft.statusId}
          onChange={(event) => onChange({ ...draft, statusId: event.target.value })}
          className={field}
        >
          <option value="">Без статуса</option>
          {statuses.map((item) => (
            <option key={item.value} value={item.value}>{item.label}</option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Исполнитель
        <select
          value={draft.assigneeId}
          onChange={(event) => onChange({ ...draft, assigneeId: event.target.value })}
          className={field}
        >
          <option value="">Не назначен</option>
          {people.map((item) => (
            <option key={item.value} value={item.value}>{item.label}</option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Описание
        <textarea
          value={draft.description}
          onChange={(event) => onChange({ ...draft, description: event.target.value })}
          rows={5}
          className={field}
        />
      </label>
      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Начало
          <input
            type="date"
            value={draft.start}
            onChange={(event) => onChange({ ...draft, start: event.target.value })}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Срок
          <input
            type="date"
            value={draft.due}
            onChange={(event) => onChange({ ...draft, due: event.target.value })}
            className={field}
          />
        </label>
      </div>
      <label className="flex flex-col gap-1 text-sm">
        Комментарий
        <textarea
          value={draft.notes}
          onChange={(event) => onChange({ ...draft, notes: event.target.value })}
          rows={3}
          className={field}
        />
      </label>
      {issue.comments.length > 0 && !creating && (
        <ul className="space-y-2 text-sm text-[var(--fg-secondary)]">
          {issue.comments.map((comment) => (
            <li key={`${comment.id ?? ""}-${comment.at}`}>{comment.text}</li>
          ))}
        </ul>
      )}
      <button
        type="submit"
        disabled={busy}
        className="w-fit rounded-md bg-[var(--accent)] px-3 py-1.5 text-sm text-[var(--accent-fg)] disabled:opacity-50"
      >
        {creating ? "Создать" : "Сохранить"}
      </button>
    </form>
  );
}
