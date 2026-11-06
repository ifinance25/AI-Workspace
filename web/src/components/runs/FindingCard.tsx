// Карточка находки: вкладки (суть, документы, PDF, история), решение проверяющего.
import { useEffect, useMemo, useState } from "react";
import ShotCarousel, { type Shot } from "@/components/runs/ShotCarousel";
import RedmineExportModal from "@/components/runs/RedmineExportModal";
import {
  FINDING_CARD_TABS,
  openPdfInFindingCard,
  type FindingCardTab,
  type PdfViewState,
} from "@/components/runs/findingCardTabs";
import {
  assetUrl,
  errorText,
  runsApi,
  type DecisionAction,
  type FindingDetail,
  type FindingImage,
  type ReviewStatus,
  type RunDetail,
} from "@/components/runs/runsApi";
import {
  ACTION_LABEL,
  EDIT_STATE_LABEL,
  LIFECYCLE_LABEL,
  REASONS,
  ROLE_LABEL,
  STATUS_LABEL,
  availableActions,
  displayStatus,
  formatStamp,
  statusTone,
} from "@/components/runs/runsLabels";

interface Props {
  projectId: number;
  run: RunDetail;
  finding: FindingDetail;
  canDecide: boolean;
  onDecided: () => void;
}

const NEEDS_FORM: DecisionAction[] = ["reject", "clarify", "edits_applied"];

function Shots({
  items,
  projectId,
  runId,
  onPdfLink,
}: {
  items: FindingImage[];
  projectId: number;
  runId: number;
  onPdfLink: (pdf: string, page?: number | null) => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const shots: Shot[] = items.flatMap((item) =>
    item.asset_id === null
      ? []
      : [{ src: assetUrl(projectId, runId, item.asset_id), doc: item.doc, page: item.page, quote: item.quote }],
  );
  if (items.length === 0) return <p className="text-sm text-[var(--fg-secondary)]">Снимков нет.</p>;
  return (
    <>
      <div className="grid gap-3 md:grid-cols-2">
        {items.map((item, index) => (
          <figure key={`${item.img}-${index}`} className="rounded-lg border border-[var(--border-subtle)] p-2">
            <figcaption className="mb-1 text-xs text-[var(--fg-secondary)]">
              <b>{item.doc}</b>
              {item.pdf && item.page ? (
                <>
                  {", "}
                  <button
                    type="button"
                    className="underline"
                    onClick={(e) => {
                      e.preventDefault();
                      onPdfLink(item.pdf as string, item.page);
                    }}
                  >
                    стр. {item.page}
                  </button>
                </>
              ) : null}
              {item.quote ? ` · «${item.quote}»` : ""}
            </figcaption>
            {item.asset_id !== null && (
              <button
                type="button"
                className="block w-full cursor-zoom-in text-left"
                onClick={() =>
                  setOpen(items.slice(0, index).filter((x) => x.asset_id !== null).length)
                }
              >
                <img
                  src={assetUrl(projectId, runId, item.asset_id)}
                  alt={`Фрагмент ${item.doc}`}
                  loading="lazy"
                  className="w-full rounded"
                />
              </button>
            )}
          </figure>
        ))}
      </div>
      {open !== null && (
        <ShotCarousel
          shots={shots}
          index={open}
          onIndex={setOpen}
          onClose={() => setOpen(null)}
          onOpenPdf={(doc, page) => {
            const pdfName = items.find((x) => x.doc === doc)?.pdf ?? doc;
            onPdfLink(pdfName, page);
          }}
        />
      )}
    </>
  );
}

export default function FindingCard({ projectId, run, finding, canDecide, onDecided }: Props) {
  const [activeTab, setActiveTab] = useState<FindingCardTab>("essence");
  const [pdfView, setPdfView] = useState<PdfViewState | null>(null);
  const [action, setAction] = useState<DecisionAction | null>(null);
  const [why, setWhy] = useState("");
  const [reason, setReason] = useState("");
  const [docRef, setDocRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [redmineOpen, setRedmineOpen] = useState(false);

  useEffect(() => {
    setActiveTab("essence");
    setPdfView(null);
  }, [finding.id]);

  const openPdfLink = (pdfName: string, page?: number | null) => {
    const next = openPdfInFindingCard(pdfName, page);
    setActiveTab(next.tab);
    setPdfView(next.pdf);
  };

  const pdfAsset = pdfView ? run.docs.find((d) => d.name === pdfView.name) : undefined;

  const manifestDocNames = useMemo(
    () => new Set(run.documents.map((d) => d.name)),
    [run.documents],
  );

  const refLabels = useMemo(
    () => new Set(finding.refs.map((r) => r.label.trim())),
    [finding.refs],
  );

  const clausesDeduped = useMemo(
    () => finding.clauses.filter((c) => !refLabels.has(c.trim())),
    [finding.clauses, refLabels],
  );

  const hasTraceabilityBlock =
    finding.refs.length > 0 || clausesDeduped.length > 0 || finding.scenarios.length > 0;

  const actions = availableActions(finding);

  const submit = async (chosen: DecisionAction) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const result = await runsApi.decide(projectId, run.id, finding.id, {
        action: chosen,
        expected_seq: finding.decision_seq,
        request_key: `${finding.id}-${finding.decision_seq}-${chosen}`,
        why,
        reason_code: reason,
        doc_ref: docRef,
      });
      if (result.files_stale) {
        setNote("Решение сохранено. Файл markdown обновится при следующем открытии прогона.");
      }
      setAction(null);
      setWhy("");
      setReason("");
      setDocRef("");
      onDecided();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const click = (chosen: DecisionAction) => {
    if (NEEDS_FORM.includes(chosen)) {
      setAction(chosen);
      setError(null);
      return;
    }
    void submit(chosen);
  };

  const formValid =
    action === "reject"
      ? Boolean(reason && why.trim())
      : action === "clarify"
        ? Boolean(why.trim())
        : action === "edits_applied"
          ? Boolean(docRef.trim())
          : false;

  return (
    <article className="space-y-5" aria-label={finding.gid}>
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-xl font-semibold">{finding.gid}</h2>
        <span className={`rounded-full px-2.5 py-0.5 text-xs ${statusTone(finding)}`}>
          {displayStatus(finding)}
        </span>
        {finding.defect_class === "traceability_break" && (
          <span className="rounded-full bg-[color-mix(in_srgb,var(--accent-brand)_22%,transparent)] px-2.5 py-0.5 text-xs">
            Разрыв прослеживаемости
          </span>
        )}
        {finding.defect_class === "stand_defect" && (
          <span className="rounded-full bg-[var(--status-warning-bg)] px-2.5 py-0.5 text-xs text-[var(--status-warning-fg)]">
            Дефект стенда
          </span>
        )}
        <span className="rounded-full bg-[var(--bg-hover)] px-2.5 py-0.5 text-xs">
          {finding.severity_raw}
        </span>
        <span className="text-sm text-[var(--fg-secondary)]">{finding.doc}</span>
      </header>
      <p className="text-sm text-[var(--fg-secondary)]">{finding.category}</p>

      <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-sidebar)] p-3">
        <h3 className="mb-2 text-sm font-medium">Решение проверяющего</h3>
        {!canDecide && (
          <p className="text-sm text-[var(--fg-secondary)]">
            Статус ставят менеджер проекта, тестировщик, бизнес- и системный аналитик.
          </p>
        )}
        {canDecide && (
          <div className="flex flex-wrap gap-2">
            {(Object.keys(ACTION_LABEL) as DecisionAction[]).map((item) => (
              <button
                key={item}
                type="button"
                disabled={busy || !actions.includes(item)}
                onClick={() => click(item)}
                aria-pressed={action === item}
                className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm disabled:opacity-40"
              >
                {ACTION_LABEL[item]}
              </button>
            ))}
          </div>
        )}
        {canDecide && action && (
          <div className="mt-3 space-y-2">
            {action === "reject" && (
              <select
                aria-label="Причина отклонения"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-transparent px-2 py-1.5 text-sm"
              >
                <option value="">Выберите причину</option>
                {REASONS.map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.label}
                  </option>
                ))}
              </select>
            )}
            {action === "edits_applied" ? (
              <input
                aria-label="Версия документа с правками"
                value={docRef}
                onChange={(e) => setDocRef(e.target.value)}
                maxLength={300}
                placeholder="Версия документа с правками, например ПМИ1 от 02.11.2026"
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-transparent px-2 py-1.5 text-sm"
              />
            ) : (
              <textarea
                aria-label="Пояснение"
                value={why}
                onChange={(e) => setWhy(e.target.value)}
                maxLength={2000}
                rows={3}
                placeholder="Пояснение. Не пишите сюда пароли, ключи и личные данные."
                className="w-full rounded-lg border border-[var(--border-subtle)] bg-transparent px-2 py-1.5 text-sm"
              />
            )}
            <div className="flex gap-2">
              <button
                type="button"
                disabled={busy || !formValid}
                onClick={() => void submit(action)}
                className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-sm text-white disabled:opacity-40"
              >
                Сохранить: {ACTION_LABEL[action]}
              </button>
              <button
                type="button"
                onClick={() => setAction(null)}
                className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm"
              >
                Отмена
              </button>
            </div>
          </div>
        )}
        <div className="mt-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-3">
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--fg-secondary)]">
            Выгрузка в Redmine
          </h4>
          <p className="mb-2 text-xs text-[var(--fg-secondary)]">
            Создать задачу из подтверждённой находки (один запрос с вашим ключом).
          </p>
          <button
            type="button"
            disabled={finding.review_status !== "confirmed"}
            onClick={() => setRedmineOpen(true)}
            className="rounded-lg bg-[var(--bg-hover)] px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Задача в Redmine
          </button>
        </div>
        {error && <p role="alert" className="alert-error mt-2">{error}</p>}
        {note && <p className="alert-success mt-2">{note}</p>}
      </section>

      <RedmineExportModal
        projectId={projectId}
        runId={run.id}
        findingId={finding.id}
        decisionSeq={finding.decision_seq}
        open={redmineOpen}
        onClose={() => setRedmineOpen(false)}
        onExported={(url) => {
          setNote(`Задача создана: ${url}`);
          onDecided();
        }}
      />

      <div
        role="tablist"
        className="flex gap-2 overflow-x-auto border-b border-[var(--border-subtle)]"
        aria-label="Разделы карточки находки"
      >
        {FINDING_CARD_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={activeTab === t.id}
            aria-controls={`finding-tab-${t.id}`}
            id={`finding-tab-btn-${t.id}`}
            onClick={() => setActiveTab(t.id)}
            className={`shrink-0 px-3 py-2 text-sm font-medium transition-colors sm:px-4 ${
              activeTab === t.id
                ? "border-b-2 border-[var(--accent)] text-[var(--accent)]"
                : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "essence" && (
        <div
          role="tabpanel"
          id="finding-tab-essence"
          aria-labelledby="finding-tab-btn-essence"
          className="space-y-5"
        >
          <section className="rounded-lg border border-[var(--status-error-border)] bg-[var(--status-error-bg)] p-3">
            <h3 className="mb-1 text-sm font-medium">Суть несоответствия</h3>
            <p className="whitespace-pre-wrap text-sm">{finding.summary}</p>
          </section>

          <section>
            <h3 className="mb-2 text-sm font-medium">Что и где нужно исправить</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-[var(--fg-secondary)]">
                  <tr>
                    <th className="py-1 pr-3 font-normal">Где</th>
                    <th className="py-1 pr-3 font-normal">Было</th>
                    <th className="py-1 pr-3 font-normal">Стало</th>
                    <th className="py-1 font-normal">Состояние</th>
                  </tr>
                </thead>
                <tbody>
                  {finding.edits.map((edit) => (
                    <tr key={edit.edit_key} className="border-t border-[var(--border-subtle)] align-top">
                      <td className="py-1 pr-3">{edit.place || edit.doc}</td>
                      <td className="py-1 pr-3 text-[var(--status-error-fg)] line-through">
                        {edit.old_text || "(пусто)"}
                      </td>
                      <td className="py-1 pr-3 text-[var(--status-success-fg)]">
                        {edit.new_text || "(удалить)"}
                      </td>
                      <td className="py-1">
                        {EDIT_STATE_LABEL[edit.state] ?? edit.state}
                        {edit.doc_ref ? ` · ${edit.doc_ref}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-lg border border-[var(--border-subtle)] p-3">
            <h3 className="mb-1 text-sm font-medium">Почему агенты так решили</h3>
            <p className="whitespace-pre-wrap text-sm">{finding.why || "Не указано."}</p>
            <p className="mt-2 whitespace-pre-wrap text-sm text-[var(--fg-secondary)]">
              <b>Проверка скептика: {finding.llm_verdict}.</b> {finding.llm_verdict_reason}
            </p>
          </section>

          {hasTraceabilityBlock && (
            <section className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-sidebar)] p-3">
              <h3 className="mb-2 text-sm font-medium">Контекст прослеживаемости</h3>
              {finding.redmine_links.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-[var(--fg-secondary)]">Задачи Redmine</p>
                  <p className="text-sm">
                    {finding.redmine_links.map((link, index) => (
                      <a
                        key={link}
                        href={link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mr-3 underline"
                      >
                        #{finding.redmine[index]}
                      </a>
                    ))}
                  </p>
                </div>
              )}
              {(finding.refs.length > 0 || clausesDeduped.length > 0) && (
                <div className="mb-2">
                  <p className="text-xs text-[var(--fg-secondary)]">Пункты / требования</p>
                  <ul className="list-inside list-disc text-sm">
                    {finding.refs.map((ref) => (
                      <li key={ref.label}>
                        <button
                          type="button"
                          className="underline"
                          onClick={(e) => {
                            e.preventDefault();
                            openPdfLink(ref.pdf, ref.page);
                          }}
                        >
                          {ref.label}
                        </button>
                      </li>
                    ))}
                    {clausesDeduped.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
              {finding.scenarios.length > 0 && (
                <div>
                  <p className="text-xs text-[var(--fg-secondary)]">Сценарии</p>
                  <ul className="list-inside list-disc text-sm">
                    {finding.scenarios.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}
        </div>
      )}

      {activeTab === "documents" && (
        <div
          role="tabpanel"
          id="finding-tab-documents"
          aria-labelledby="finding-tab-btn-documents"
          className="space-y-5"
        >
          <section>
            <h3 className="mb-2 text-sm font-medium">Документы прогона</h3>
            {run.documents.length === 0 && run.docs.length === 0 ? (
              <p className="text-sm text-[var(--fg-secondary)]">Список документов пуст.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {run.documents.map((doc) => {
                  const asset = run.docs.find((d) => d.name === doc.name);
                  return (
                    <li key={doc.name} className="flex flex-wrap items-baseline gap-2">
                      <span>
                        {doc.name}
                        {typeof doc.role === "string" && doc.role ? (
                          <span className="text-[var(--fg-secondary)]"> · {doc.role}</span>
                        ) : null}
                      </span>
                      {asset ? (
                        <button
                          type="button"
                          className="underline"
                          onClick={(e) => {
                            e.preventDefault();
                            openPdfLink(doc.name, null);
                          }}
                        >
                          Открыть PDF
                        </button>
                      ) : null}
                    </li>
                  );
                })}
                {run.docs
                  .filter((d) => !manifestDocNames.has(d.name))
                  .map((d) => (
                    <li key={`asset-${d.id}`}>
                      {d.name}{" "}
                      <button
                        type="button"
                        className="underline"
                        onClick={(e) => {
                          e.preventDefault();
                          openPdfLink(d.name, null);
                        }}
                      >
                        Открыть PDF
                      </button>
                    </li>
                  ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-sm font-medium">Документы: на что опирались</h3>
            <Shots
              items={finding.evidence}
              projectId={projectId}
              runId={run.id}
              onPdfLink={openPdfLink}
            />
          </section>
          {finding.marked.length > 0 && (
            <section>
              <h3 className="mb-2 text-sm font-medium">Страница ПМИ с правками</h3>
              <Shots
                items={finding.marked}
                projectId={projectId}
                runId={run.id}
                onPdfLink={openPdfLink}
              />
            </section>
          )}
        </div>
      )}

      {activeTab === "pdf" && (
        <div
          role="tabpanel"
          id="finding-tab-pdf"
          aria-labelledby="finding-tab-btn-pdf"
          className="rounded-lg border border-[var(--border-subtle)] p-2"
        >
          {pdfView ? (
            <>
              <p className="mb-2 text-sm">
                {pdfView.name}
                {pdfView.page ? `, стр. ${pdfView.page}` : ""}
              </p>
              {pdfAsset ? (
                <iframe
                  key={`${pdfView.name}-${pdfView.page ?? 0}`}
                  title={pdfView.name}
                  data-testid="finding-pdf-iframe"
                  src={assetUrl(projectId, run.id, pdfAsset.id, pdfView.page)}
                  className="h-[60vh] w-full rounded bg-white"
                />
              ) : (
                <p className="text-sm text-[var(--fg-secondary)]">Документа нет в прогоне.</p>
              )}
            </>
          ) : (
            <p className="text-sm text-[var(--fg-secondary)]">
              Нажмите ссылку на документ или страницу в блоке «Контекст прослеживаемости» или на вкладке
              «Документы».
            </p>
          )}
        </div>
      )}

      {activeTab === "history" && (
        <div
          role="tabpanel"
          id="finding-tab-history"
          aria-labelledby="finding-tab-btn-history"
        >
          {finding.history.length === 0 ? (
            <p className="text-sm text-[var(--fg-secondary)]">Решений пока нет.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {finding.history.map((item) => {
                const actionShown =
                  ACTION_LABEL[item.action as DecisionAction] ?? item.action;
                const statusShown =
                  STATUS_LABEL[item.review_to as ReviewStatus] ?? item.review_to;
                const dupStatus =
                  typeof actionShown === "string" &&
                  typeof statusShown === "string" &&
                  actionShown.replace(/\.$/, "").trim().toLowerCase() === statusShown.trim().toLowerCase();
                const whyTrim = item.why?.trim() ?? "";
                return (
                  <li key={item.decision_key}>
                    <span className="text-[var(--fg-secondary)]">
                      {formatStamp(item.at)} · {item.actor} (
                      {ROLE_LABEL[item.actor_role] ?? item.actor_role})
                    </span>
                    {dupStatus ? (
                      <>
                        {" "}
                        <b>{actionShown}</b>
                        {whyTrim ? ` · ${whyTrim}` : ""}
                      </>
                    ) : (
                      <>
                        {" · "}
                        <b>{actionShown}</b>
                        {`. Статус «${statusShown}», этап «${LIFECYCLE_LABEL[item.lifecycle_to] ?? item.lifecycle_to}»`}
                        {whyTrim ? ` · ${whyTrim}` : ""}
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}
