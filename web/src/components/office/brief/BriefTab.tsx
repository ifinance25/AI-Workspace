import { useCallback, useEffect, useState, type ChangeEvent } from "react";

import type { OfficeProject } from "@/components/office/officeApi";
import {
  ACCEPTED_BRIEF_FILES,
  briefApi,
  errorText,
  type BriefSaveResult,
  type BriefVersion,
  type BriefVersionFull,
} from "@/components/office/brief/briefApi";
import { Markdown } from "@/lib/Markdown";

// Вкладка «Бриф»: текст (вставка или диктовка устройства) или файл .md/.txt/.docx
// становится новой версией Markdown. Список версий: номер, дата, источник.
export interface BriefTabProps {
  project: OfficeProject;
}

const EMPTY_HINT = "Положите бриф: вставьте или надиктуйте текст либо загрузите файл .md, .txt, .docx.";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("ru-RU");
}

export default function BriefTab({ project }: BriefTabProps) {
  const [versions, setVersions] = useState<BriefVersion[] | null>(null);
  const [selected, setSelected] = useState<BriefVersionFull | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const open = useCallback(
    async (number: number) => {
      try {
        setSelected(await briefApi.getVersion(project.id, number));
      } catch (err) {
        setError(errorText(err));
      }
    },
    [project.id],
  );

  const reload = useCallback(
    async (show?: number) => {
      const list = await briefApi.listVersions(project.id);
      setVersions(list);
      const target = show ?? list[list.length - 1]?.number;
      if (target !== undefined) await open(target);
    },
    [project.id, open],
  );

  useEffect(() => {
    reload().catch((err) => setError(errorText(err)));
  }, [reload]);

  async function save(run: () => Promise<BriefSaveResult>) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const result = await run();
      if (!result.created) setNotice(`Такой текст уже есть в версии ${result.version.number}.`);
      await reload(result.version.number);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  function saveText() {
    if (!text.trim()) {
      setError(EMPTY_HINT);
      return;
    }
    void save(() => briefApi.saveText(project.id, text));
  }

  function uploadFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void save(() => briefApi.uploadFile(project.id, file));
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <label htmlFor="brief-text" className="text-sm font-medium text-[var(--fg-primary)]">
          Текст брифа
        </label>
        <textarea
          id="brief-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={8}
          placeholder="Вставьте или надиктуйте бриф. Можно в Markdown."
          className="w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-input)] p-3 text-sm text-[var(--fg-primary)]"
        />
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={saveText}
            disabled={busy}
            className="rounded-md bg-[var(--accent)] px-3 py-1.5 text-sm text-[var(--accent-fg)] hover:opacity-90 disabled:opacity-50"
          >
            Сохранить версию
          </button>
          <label className="cursor-pointer text-sm text-[var(--fg-muted)] underline">
            Загрузить файл
            <input
              type="file"
              accept={ACCEPTED_BRIEF_FILES}
              onChange={uploadFile}
              disabled={busy}
              className="sr-only"
            />
          </label>
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
        {notice && <p className="text-sm text-[var(--fg-muted)]">{notice}</p>}
      </div>

      {versions !== null && versions.length === 0 && (
        <p className="text-sm text-[var(--fg-muted)]">Брифа ещё нет. {EMPTY_HINT}</p>
      )}

      {versions !== null && versions.length > 0 && (
        <div className="flex flex-col gap-3 md:flex-row">
          <ul className="flex shrink-0 flex-col gap-1 md:w-64" aria-label="Версии брифа">
            {[...versions].reverse().map((v) => (
              <li key={v.id}>
                <button
                  type="button"
                  onClick={() => void open(v.number)}
                  aria-current={selected?.number === v.number ? "true" : undefined}
                  className={`w-full rounded-md px-2 py-1.5 text-left text-sm ${
                    selected?.number === v.number
                      ? "bg-[var(--bg-hover)] text-[var(--fg-primary)]"
                      : "text-[var(--fg-muted)] hover:bg-[var(--bg-hover)]"
                  }`}
                >
                  Версия {v.number} · {formatDate(v.created_at)} · {v.source}
                </button>
              </li>
            ))}
          </ul>
          {selected && (
            <div className="min-w-0 flex-1 rounded-md border border-[var(--border-subtle)] p-4">
              <Markdown>{selected.markdown}</Markdown>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
