// Карточка находки: суть, правки, цитаты, решение проверяющего, история.
import { useState } from "react";
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
  onOpenPdf: (pdf: string, page: number | null | undefined) => void;
}

const NEEDS_FORM: DecisionAction[] = ["reject", "clarify", "edits_applied"];

function Shots({
  items,
  projectId,
  runId,
  onOpenPdf,
}: {
  items: FindingImage[];
  projectId: number;
  runId: number;
  onOpenPdf: Props["onOpenPdf"];
}) {
  if (items.length === 0) return <p className="text-sm text-[var(--fg-secondary)]">Снимков нет.</p>;
  return (
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
                  onClick={() => onOpenPdf(item.pdf as string, item.page)}
                >
                  стр. {item.page}
                </button>
              </>
            ) : null}
            {item.quote ? ` · «${item.quote}»` : ""}
          </figcaption>
          {item.asset_id !== null && (
            <img
              src={assetUrl(projectId, runId, item.asset_id)}
              alt={`Фрагмент ${item.doc}`}
              loading="lazy"
              className="w-full rounded"
            />
          )}
        </figure>
      ))}
    </div>
  );
}

export default function FindingCard({ projectId, run, finding, canDecide, onDecided, onOpenPdf }: Props) {
  const [action, setAction] = useState<DecisionAction | null>(null);
  const [why, setWhy] = useState("");
  const [reason, setReason] = useState("");
  const [docRef, setDocRef] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const actions = availableActions(finding);

  const submit = async (chosen: DecisionAction) => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const result = await runsApi.decide(projectId, run.id, finding.id, {
        action: chosen,
        expected_seq: finding.decision_seq,
        // Тот же ключ при повторном нажатии в том же состоянии: двойной клик не дублирует запись.
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
        <span className="rounded-full bg-[var(--bg-hover)] px-2.5 py-0.5 text-xs">
          {finding.severity_raw}
        </span>
        <span className="text-sm text-[var(--fg-secondary)]">{finding.doc}</span>
      </header>
      <p className="text-sm text-[var(--fg-secondary)]">{finding.category}</p>
      <p className="text-sm">
        {finding.refs.map((ref) => (
          <button
            key={ref.label}
            type="button"
            className="mr-3 underline"
            onClick={() => onOpenPdf(ref.pdf, ref.page)}
          >
            {ref.label}
          </button>
        ))}
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
                  <td className="py-1 pr-3 text-[var(--status-error-fg)] line-through">{edit.old_text || "(пусто)"}</td>
                  <td className="py-1 pr-3 text-[var(--status-success-fg)]">{edit.new_text || "(удалить)"}</td>
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

      <section>
        <h3 className="mb-2 text-sm font-medium">Документы: на что опирались</h3>
        <Shots items={finding.evidence} projectId={projectId} runId={run.id} onOpenPdf={onOpenPdf} />
      </section>
      {finding.marked.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-medium">Страница ПМИ с правками</h3>
          <Shots items={finding.marked} projectId={projectId} runId={run.id} onOpenPdf={onOpenPdf} />
        </section>
      )}

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
        {error && <p role="alert" className="alert-error mt-2">{error}</p>}
        {note && <p className="alert-success mt-2">{note}</p>}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-medium">История решений</h3>
        {finding.history.length === 0 ? (
          <p className="text-sm text-[var(--fg-secondary)]">Решений пока нет.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {finding.history.map((item) => (
              <li key={item.decision_key}>
                <span className="text-[var(--fg-secondary)]">
                  {formatStamp(item.at)} · {item.actor} (
                  {ROLE_LABEL[item.actor_role] ?? item.actor_role}) ·{" "}
                </span>
                <b>{ACTION_LABEL[item.action as DecisionAction] ?? item.action}.</b> Статус «
                {STATUS_LABEL[item.review_to as ReviewStatus] ?? item.review_to}», этап «
                {LIFECYCLE_LABEL[item.lifecycle_to] ?? item.lifecycle_to}»
                {item.why ? `. ${item.why}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>
    </article>
  );
}
