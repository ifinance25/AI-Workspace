// Экран «Прогоны»: список находок, карточка с решением, статистика, панель PDF.
import LoadingCenter from "@/components/uikit/LoadingCenter";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import FindingCard from "@/components/runs/FindingCard";
import StatsPanel from "@/components/runs/StatsPanel";
import {
  assetUrl,
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
  displayStatus,
  matchesFilter,
  statusTone,
  type StatusFilter,
} from "@/components/runs/runsLabels";

type ViewId = "cards" | "stats";

const SELECT_CLASS =
  "rounded-lg border border-[var(--border-subtle)] bg-transparent px-2 py-1.5 text-sm";

export default function RunsScreens({ projectId }: { projectId: number }) {
  const [list, setList] = useState<RunsList | null>(null);
  const [runId, setRunId] = useState<number | null>(null);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [findings, setFindings] = useState<FindingRow[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<FindingDetail | null>(null);
  const [view, setView] = useState<ViewId>("cards");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [severity, setSeverity] = useState("");
  const [doc, setDoc] = useState("");
  const [query, setQuery] = useState("");
  const [pdf, setPdf] = useState<{ name: string; page: number | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const loadList = useCallback(
    async (preferred?: number) => {
      try {
        const data = await runsApi.listRuns(projectId);
        setList(data);
        setRunId((current) => preferred ?? current ?? data.runs[0]?.id ?? null);
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
        (!needle || f.gid.toLowerCase().includes(needle) || f.summary.toLowerCase().includes(needle)),
    );
  }, [findings, status, severity, doc, query]);

  const openPdf = useCallback((name: string, page: number | null | undefined) => {
    setPdf({ name, page: page ?? null });
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

  const pdfAsset = pdf && run ? run.docs.find((d) => d.name === pdf.name) : undefined;

  if (!list && !error) return <LoadingCenter label="Загрузка прогонов…" className="min-h-[40vh]" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold sm:text-2xl">Прогоны и валидация</h1>
        {list && list.runs.length > 1 && (
          <select
            aria-label="Прогон"
            value={runId ?? ""}
            onChange={(e) => {
              setRunId(Number(e.target.value));
              setSelected(null);
              setPdf(null);
            }}
            className={SELECT_CLASS}
          >
            {list.runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title || r.run_key}
              </option>
            ))}
          </select>
        )}
      </div>

      {error && (
        <div role="alert" className="alert-error">
          {error}
        </div>
      )}
      {message && <div className="alert-success">{message}</div>}

      {list?.can_manage && (
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

      {run && (
        <>
          <div role="tablist" className="flex gap-2 border-b border-[var(--border-subtle)]">
            {(
              [
                ["cards", "Карточки"],
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

          {view === "stats" && <StatsPanel stats={run.stats} />}

          {view === "cards" && (
            <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
              <aside className="space-y-2">
                <input
                  aria-label="Поиск"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Номер или слово из сути"
                  className={`${SELECT_CLASS} w-full`}
                />
                <div className="flex flex-wrap gap-2">
                  <select
                    aria-label="Статус"
                    value={status}
                    onChange={(e) => setStatus(e.target.value as StatusFilter)}
                    className={SELECT_CLASS}
                  >
                    <option value="all">Все статусы</option>
                    {(Object.keys(STATUS_LABEL) as Array<keyof typeof STATUS_LABEL>).map((k) => (
                      <option key={k} value={k}>
                        {STATUS_LABEL[k]}
                      </option>
                    ))}
                    <option value="fixed">{FIXED_LABEL}</option>
                  </select>
                  <select
                    aria-label="Важность"
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value)}
                    className={SELECT_CLASS}
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
                    className={SELECT_CLASS}
                  >
                    <option value="">Все документы</option>
                    {docs.map((d) => (
                      <option key={d}>{d}</option>
                    ))}
                  </select>
                </div>
                <p className="text-xs text-[var(--fg-secondary)]">
                  Показано {visible.length} из {findings.length}
                </p>
                <ul className="max-h-[70vh] space-y-1 overflow-y-auto" aria-label="Находки">
                  {visible.map((f) => (
                    <li key={f.id}>
                      <button
                        type="button"
                        onClick={() => setSelected(f.id)}
                        aria-current={selected === f.id}
                        className={`w-full rounded-lg px-3 py-2 text-left text-sm ${
                          selected === f.id ? "bg-[var(--bg-hover)]" : "hover:bg-[var(--bg-hover)]"
                        }`}
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
                  ))}
                </ul>
              </aside>

              <div className="min-w-0 space-y-4">
                {pdf && (
                  <section className="rounded-lg border border-[var(--border-subtle)] p-2">
                    <div className="mb-2 flex items-center justify-between text-sm">
                      <span>
                        {pdf.name}
                        {pdf.page ? `, стр. ${pdf.page}` : ""}
                      </span>
                      <button
                        type="button"
                        onClick={() => setPdf(null)}
                        className="rounded-lg bg-[var(--bg-hover)] px-2 py-1"
                      >
                        Закрыть
                      </button>
                    </div>
                    {pdfAsset ? (
                      <iframe
                        key={`${pdf.name}-${pdf.page}`}
                        title={pdf.name}
                        src={assetUrl(projectId, run.id, pdfAsset.id, pdf.page)}
                        className="h-[60vh] w-full rounded bg-white"
                      />
                    ) : (
                      <p className="text-sm text-[var(--fg-secondary)]">Документа нет в прогоне.</p>
                    )}
                  </section>
                )}
                {detail ? (
                  <FindingCard
                    key={detail.id}
                    projectId={projectId}
                    run={run}
                    finding={detail}
                    canDecide={list?.can_decide ?? false}
                    onDecided={afterDecision}
                    onOpenPdf={openPdf}
                  />
                ) : (
                  <p className="text-sm text-[var(--fg-secondary)]">
                    Выберите находку в списке слева.
                  </p>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
