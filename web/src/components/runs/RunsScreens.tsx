// Экран «Прогоны»: список находок, карточка с решением, статистика.
import LoadingCenter from "@/components/uikit/LoadingCenter";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import FindingCard from "@/components/runs/FindingCard";
import RunsAggregateStatsPanel from "@/components/runs/RunsAggregateStatsPanel";
import RunsRegistryPanel from "@/components/runs/RunsRegistryPanel";
import RedmineStandRemediationModal from "@/components/runs/RedmineStandRemediationModal";
import {
  errorText,
  runsApi,
  type FindingDetail,
  type FindingRow,
  type RunDetail,
  type RunsList,
} from "@/components/runs/runsApi";
import {
  STATUS_LABEL,
  FIXED_LABEL,
  defectClassFilterLabel,
  displayStatus,
  matchesFilter,
  statusTone,
  type StatusFilter,
} from "@/components/runs/runsLabels";
import {
  isPendingDecision,
  loadOpenedFindingIds,
  markFindingOpened,
} from "@/components/runs/runsOpened";

import { comparisonKindLabel, formatRunDate } from "@/components/runs/runsRegistryLabels";

type ViewId = "registry" | "run" | "stats";

const SELECT_CLASS =
  "rounded-lg border border-[var(--border-subtle)] bg-transparent px-2 py-1.5 text-sm";

export default function RunsScreens({ projectId }: { projectId: number }) {
  const [list, setList] = useState<RunsList | null>(null);
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [findings, setFindings] = useState<FindingRow[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<FindingDetail | null>(null);
  const [view, setView] = useState<ViewId>("registry");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [severity, setSeverity] = useState("");
  const [doc, setDoc] = useState("");
  const [defectClass, setDefectClass] = useState("");
  const [category, setCategory] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openedIds, setOpenedIds] = useState<Set<number>>(() => new Set());
  const [standRemediationOpen, setStandRemediationOpen] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const loadList = useCallback(
    async (preferred?: number) => {
      try {
        const data = await runsApi.listRuns(projectId);
        setList(data);
        setRunId((current) => preferred ?? current ?? null);
      } catch (err) {
        setError(errorText(err));
      }
    },
    [projectId],
  );

  const loadRun = useCallback(
    async (id: number) => {
      try {
        const [info, rows] = await Promise.all([
          runsApi.getRun(projectId, id),
          runsApi.listFindings(projectId, id),
        ]);
        setRun(info);
        setFindings(rows);
        setSelected((current) => (current && rows.some((r) => r.id === current) ? current : null));
      } catch (err) {
        setError(errorText(err));
      }
    },
    [projectId],
  );

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    if (runId !== null) void loadRun(runId);
  }, [runId, loadRun]);

  useEffect(() => {
    if (!run?.stats.stand_remediation_ready || run.stand_remediation_issue_id) {
      setStandRemediationOpen(false);
      return;
    }
    const key = `office.runs.standRemediationPrompt.${projectId}.${run.id}`;
    try {
      if (sessionStorage.getItem(key)) return;
    } catch {
      /* ignore */
    }
    setStandRemediationOpen(true);
  }, [projectId, run]);

  useEffect(() => {
    if (runId === null) {
      setOpenedIds(new Set());
      return;
    }
    setOpenedIds(loadOpenedFindingIds(projectId, runId));
  }, [projectId, runId]);

  const selectFinding = useCallback(
    (findingId: number) => {
      setSelected(findingId);
      if (runId !== null) {
        setOpenedIds(markFindingOpened(projectId, runId, findingId));
      }
    },
    [projectId, runId],
  );

  useEffect(() => {
    if (runId === null || selected === null) {
      setDetail(null);
      return;
    }
    let alive = true;
    runsApi.getFinding(projectId, runId, selected).then(
      (data) => {
        if (alive) setDetail(data);
      },
      (err) => {
        if (alive) setError(errorText(err));
      },
    );
    return () => {
      alive = false;
    };
  }, [projectId, runId, selected]);

  const afterDecision = useCallback(() => {
    if (runId === null) return;
    void loadRun(runId);
    if (selected !== null) {
      void runsApi.getFinding(projectId, runId, selected).then(setDetail, (e) => setError(errorText(e)));
    }
  }, [projectId, runId, selected, loadRun]);

  const docs = useMemo(() => [...new Set(findings.map((f) => f.doc))].sort(), [findings]);
  const defectClasses = useMemo(
    () => [...new Set(findings.map((f) => f.defect_class))].filter(Boolean).sort(),
    [findings],
  );
  const categories = useMemo(
    () => [...new Set(findings.map((f) => f.category))].filter(Boolean).sort(),
    [findings],
  );
  const severities = useMemo(
    () => [...new Set(findings.map((f) => f.severity_raw))],
    [findings],
  );
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return findings.filter(
      (f) =>
        matchesFilter(f, status) &&
        (!severity || f.severity_raw === severity) &&
        (!doc || f.doc === doc) &&
        (!defectClass || f.defect_class === defectClass) &&
        (!category || f.category === category) &&
        (!needle || f.gid.toLowerCase().includes(needle) || f.summary.toLowerCase().includes(needle)),
    );
  }, [findings, status, severity, doc, defectClass, category, query]);

  const runStatusSummary = useMemo(() => {
    if (!run) return null;
    const by = run.stats.by_status ?? {};
    const fixedCount = findings.filter((f) => f.lifecycle === "fixed").length;
    return {
      total: run.stats.total,
      new: by.new ?? 0,
      needs_info: by.needs_info ?? 0,
      confirmed: by.confirmed ?? 0,
      rejected: by.rejected ?? 0,
      fixed: fixedCount,
      pending_decision: run.stats.pending_decision,
      reviewed: run.stats.reviewed,
    };
  }, [run, findings]);

  const pendingVisible = useMemo(
    () => visible.filter((f) => isPendingDecision(f.review_status)),
    [visible],
  );

  const jumpNextPending = useCallback(() => {
    if (pendingVisible.length === 0) return;
    const currentIdx = selected ? pendingVisible.findIndex((f) => f.id === selected) : -1;
    const next = pendingVisible[(currentIdx + 1) % pendingVisible.length];
    selectFinding(next.id);
  }, [pendingVisible, selected, selectFinding]);

  useEffect(() => {
    if (view !== "run") return;
    const onKey = (event: KeyboardEvent) => {
      if (document.querySelector('[role=dialog][aria-modal="true"]')) return;
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (visible.length === 0) return;
      const idx = selected ? visible.findIndex((f) => f.id === selected) : -1;
      if (event.key === "j" || event.key === "ArrowDown") {
        event.preventDefault();
        const next = visible[Math.min(visible.length - 1, idx + 1)];
        if (next) selectFinding(next.id);
      } else if (event.key === "k" || event.key === "ArrowUp") {
        event.preventDefault();
        const next = visible[Math.max(0, idx <= 0 ? 0 : idx - 1)];
        if (next) selectFinding(next.id);
      } else if (event.key === "Enter" && idx >= 0) {
        event.preventDefault();
        selectFinding(visible[idx].id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, visible, selected, selectFinding]);

  const openRun = useCallback((id: number) => {
    setRunId(id);
    setSelected(null);
    setView("run");
  }, []);

  const backToRegistry = useCallback(() => {
    setView("registry");
    setSelected(null);
  }, []);

  const importFile = async (file: File) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await runsApi.importRun(projectId, file);
      setMessage(
        result.duplicate
          ? "Этот прогон уже загружен."
          : `Прогон загружен: находок ${result.findings}, файлов ${result.assets}.`,
      );
      await loadList(result.run_id);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const togglePolicy = async () => {
    if (!list) return;
    setError(null);
    try {
      const next = list.export_ban === "none" ? "all_external" : "none";
      await runsApi.setPolicy(projectId, next);
      setList({ ...list, export_ban: next });
    } catch (err) {
      setError(errorText(err));
    }
  };

  const download = async () => {
    if (runId === null || !run) return;
    setError(null);
    try {
      const blob = await runsApi.exportRun(projectId, runId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${run.run_key}-markdown.zip`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(errorText(err));
    }
  };

  if (!list && !error) return <LoadingCenter label="Загрузка прогонов…" className="min-h-[40vh]" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold sm:text-2xl">Прогоны и валидация</h1>
      </div>

      {error && (
        <div role="alert" className="alert-error">
          {error}
        </div>
      )}
      {message && <div className="alert-success">{message}</div>}

      {list?.can_manage && view === "registry" && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-[var(--border-subtle)] p-3 text-sm">
          <input
            ref={fileInput}
            type="file"
            accept=".zip,application/zip"
            hidden
            data-testid="import-input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void importFile(file);
            }}
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => fileInput.current?.click()}
            className="rounded-lg bg-[var(--accent-brand)] px-3 py-1.5 text-white hover:opacity-90 disabled:opacity-40"
          >
            Загрузить прогон
          </button>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={list.export_ban === "none"}
              onChange={() => void togglePolicy()}
            />
            Разрешить вывоз markdown внешней модели
          </label>
          <button
            type="button"
            disabled={list.export_ban !== "none" || runId === null}
            onClick={() => void download()}
            className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 disabled:opacity-40"
          >
            Скачать markdown для LLM
          </button>
        </div>
      )}

      {list && list.runs.length === 0 && (
        <p className="text-sm text-[var(--fg-secondary)]">
          Прогонов пока нет.{" "}
          {list.can_manage ? "Загрузите пакет прогона кнопкой выше." : "Пакет загружает менеджер проекта."}
        </p>
      )}

      {list && list.runs.length > 0 && view !== "run" && (
        <div role="tablist" className="flex gap-2 border-b border-[var(--border-subtle)]">
          {(
            [
              ["registry", "Реестр прогонов"],
              ["stats", "Статистика"],
            ] as Array<[ViewId, string]>
          ).map(([id, label]) => (
            <button
              key={id}
              role="tab"
              aria-selected={view === id}
              onClick={() => setView(id)}
              className={`px-4 py-2 text-sm font-medium ${
                view === id
                  ? "border-b-2 border-[var(--accent)] text-[var(--accent)]"
                  : "text-[var(--fg-secondary)]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {view === "registry" && list && (
        <RunsRegistryPanel runs={list.runs} activeRunId={runId} onOpenRun={openRun} />
      )}

      {view === "stats" && list && (
        <RunsAggregateStatsPanel runs={list.runs} onOpenRun={openRun} />
      )}

      {view === "run" && runId !== null && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={backToRegistry}
              className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm"
            >
              ← Назад
            </button>
            {run ? (
              <div className="text-sm">
                <span className="font-semibold">{run.title || run.run_key}</span>
                <span className="ml-2 text-[var(--fg-secondary)]">
                  {comparisonKindLabel(run.comparison_kind)} ·{" "}
                  {formatRunDate(run.display_at ?? run.imported_at)}
                </span>
              </div>
            ) : (
              <span className="text-sm text-[var(--fg-secondary)]">Загрузка прогона…</span>
            )}
          </div>

          {!run ? (
            <LoadingCenter label="Загрузка прогона…" className="min-h-[30vh]" />
          ) : (
            <>
              {run.source_kind === "stand_run" && (
                <p
                  className="rounded-lg border border-[color-mix(in_srgb,var(--accent-brand)_35%,transparent)] bg-[color-mix(in_srgb,var(--accent-brand)_10%,transparent)] px-3 py-2 text-sm text-[var(--fg-secondary)]"
                  data-testid="stand-run-hint"
                >
                  Прогон соответствия стенда документации: карточки с классом «дефект стенда» описывают
                  расхождение поведения стенда с ПМИ/ФТТ. После разбора всех находок можно создать
                  сводный тикет Redmine на исправление стенда.
                </p>
              )}
              {(run.stats.stand_remediation_ready && !run.stand_remediation_issue_id) ||
              run.stand_remediation_issue_id ? (
                <div className="space-y-2">
                  {run.stats.stand_remediation_ready && !run.stand_remediation_issue_id && (
                    <button
                      type="button"
                      data-testid="stand-remediation-btn"
                      onClick={() => setStandRemediationOpen(true)}
                      className="rounded-lg bg-[var(--accent)] px-3 py-2 text-sm text-white"
                    >
                      Создать тикет Redmine на исправление стенда
                    </button>
                  )}
                  {run.stand_remediation_issue_id ? (
                    <p className="text-sm text-[var(--fg-secondary)]">
                      Сводный тикет на исправление стенда: #{run.stand_remediation_issue_id}
                    </p>
                  ) : null}
                </div>
              ) : null}
              <section className="w-full max-w-none space-y-3" aria-label="Фильтры и поиск">
                <input
                  aria-label="Поиск"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Номер или слово из сути"
                  className={`${SELECT_CLASS} w-full max-w-none`}
                />
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={pendingVisible.length === 0}
                    onClick={jumpNextPending}
                    className="rounded-lg bg-[var(--bg-hover)] px-2 py-1 text-xs disabled:opacity-40"
                  >
                    Следующая без решения
                  </button>
                  <span className="text-xs text-[var(--fg-secondary)]">
                    осталось {pendingVisible.length}
                  </span>
                </div>
                <div className="flex w-full flex-wrap gap-2">
                  <select
                    aria-label="Статус"
                    value={status}
                    onChange={(e) => setStatus(e.target.value as StatusFilter)}
                    className={`${SELECT_CLASS} min-w-0 flex-1 basis-[11rem] sm:basis-auto sm:flex-none`}
                  >
                    <option value="all">Все статусы</option>
                    {(Object.keys(STATUS_LABEL) as Array<keyof typeof STATUS_LABEL>).map((k) => (
                      <option key={k} value={k}>
                        {STATUS_LABEL[k]}
                      </option>
                    ))}
                    <option value="undecided">Без решения</option>
                    <option value="traceability">Разрыв прослеживаемости</option>
                    <option value="stand_defect">Дефект стенда</option>
                    <option value="fixed">{FIXED_LABEL}</option>
                  </select>
                  <select
                    aria-label="Важность"
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value)}
                    className={`${SELECT_CLASS} min-w-0 flex-1 basis-[11rem] sm:basis-auto sm:flex-none`}
                  >
                    <option value="">Любая важность</option>
                    {severities.map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                  <select
                    aria-label="Документ"
                    value={doc}
                    onChange={(e) => setDoc(e.target.value)}
                    className={`${SELECT_CLASS} min-w-0 flex-1 basis-[11rem] sm:basis-auto sm:flex-none`}
                  >
                    <option value="">Все документы</option>
                    {docs.map((d) => (
                      <option key={d}>{d}</option>
                    ))}
                  </select>
                  <select
                    aria-label="Класс находки"
                    value={defectClass}
                    onChange={(e) => setDefectClass(e.target.value)}
                    className={`${SELECT_CLASS} min-w-0 flex-1 basis-[11rem] sm:basis-auto sm:flex-none`}
                  >
                    <option value="">Все классы</option>
                    {defectClasses.map((c) => (
                      <option key={c} value={c}>
                        {defectClassFilterLabel(c)}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label="Категория"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className={`${SELECT_CLASS} min-w-0 flex-1 basis-[11rem] sm:basis-auto sm:flex-none`}
                  >
                    <option value="">Все категории</option>
                    {categories.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
                <p className="text-xs text-[var(--fg-secondary)]">
                  Показано {visible.length} из {findings.length}
                </p>
              </section>
              <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
                <aside className="min-w-0 space-y-2">
                  <ul
                    ref={listRef}
                    className="max-h-[70vh] space-y-1 overflow-y-auto"
                    aria-label="Находки"
                  >
                    {visible.map((f) => {
                      const openedPending =
                        openedIds.has(f.id) && isPendingDecision(f.review_status);
                      return (
                        <li key={f.id}>
                          <button
                            type="button"
                            onClick={() => selectFinding(f.id)}
                            aria-current={selected === f.id}
                            className={`w-full rounded-lg px-3 py-2 text-left text-sm ${
                              selected === f.id ? "bg-[var(--bg-hover)]" : "hover:bg-[var(--bg-hover)]"
                            } ${openedPending ? "ring-1 ring-[var(--accent-brand)]" : ""}`}
                          >
                            <span className="flex items-center justify-between gap-2">
                              <b>{f.gid}</b>
                              <span className={`rounded-full px-2 py-0.5 text-xs ${statusTone(f)}`}>
                                {displayStatus(f)}
                              </span>
                            </span>
                            <span className="line-clamp-2 text-xs text-[var(--fg-secondary)]">
                              {f.severity_raw} · {f.doc} · {f.summary}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </aside>

                <div className="min-w-0 space-y-4">
                  {detail ? (
                    <FindingCard
                      key={detail.id}
                      projectId={projectId}
                      run={run}
                      finding={detail}
                      canDecide={list?.can_decide ?? false}
                      onDecided={afterDecision}
                    />
                  ) : runStatusSummary ? (
                    <section
                      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-sidebar)] p-4"
                      aria-label="Сводка по прогону"
                    >
                      <h3 className="mb-3 text-sm font-medium">Сводка по прогону</h3>
                      <p className="mb-2 text-xs text-[var(--fg-secondary)]">
                        Всего находок: {runStatusSummary.total}. Разобрано записей: {runStatusSummary.reviewed}.
                        {runStatusSummary.pending_decision > 0
                          ? ` Осталось без финального решения: ${runStatusSummary.pending_decision}.`
                          : ""}
                      </p>
                      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                        <li>
                          <span className="text-[var(--fg-secondary)]">{STATUS_LABEL.confirmed}:</span>{" "}
                          <b>{runStatusSummary.confirmed}</b>
                        </li>
                        <li>
                          <span className="text-[var(--fg-secondary)]">{STATUS_LABEL.new}:</span>{" "}
                          <b>{runStatusSummary.new}</b>
                        </li>
                        <li>
                          <span className="text-[var(--fg-secondary)]">{STATUS_LABEL.needs_info}:</span>{" "}
                          <b>{runStatusSummary.needs_info}</b>
                        </li>
                        <li>
                          <span className="text-[var(--fg-secondary)]">{STATUS_LABEL.rejected}:</span>{" "}
                          <b>{runStatusSummary.rejected}</b>
                        </li>
                        <li>
                          <span className="text-[var(--fg-secondary)]">{FIXED_LABEL}:</span>{" "}
                          <b>{runStatusSummary.fixed}</b>
                        </li>
                      </ul>
                    </section>
                  ) : (
                    <p className="text-sm text-[var(--fg-secondary)]">Загрузка сводки…</p>
                  )}
                </div>
              </div>
            </>
          )}
        </>
      )}

      {run && (
        <RedmineStandRemediationModal
          projectId={projectId}
          runId={run.id}
          runKey={run.run_key}
          confirmedCount={run.stats.confirmed_stand_defects ?? 0}
          open={standRemediationOpen}
          onClose={() => {
            const key = `office.runs.standRemediationPrompt.${projectId}.${run.id}`;
            try {
              sessionStorage.setItem(key, "1");
            } catch {
              /* ignore */
            }
            setStandRemediationOpen(false);
          }}
          onExported={(url) => {
            setMessage(`Сводный тикет создан: ${url}`);
            void loadRun(run.id);
          }}
        />
      )}
    </div>
  );
}
