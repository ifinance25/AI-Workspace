import { useEffect, useRef, useState } from "react";
import SheetTable from "./SheetTable";

// Защита от подвисания UI на гигантских таблицах.
const MAX_TABLE_ROWS = 5000;

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center p-6 text-center text-sm text-[var(--fg-muted)]">
      {children}
    </div>
  );
}

async function fetchBytes(url: string): Promise<ArrayBuffer> {
  const resp = await fetch(url, { credentials: "include" });
  if (!resp.ok) {
    if (resp.status === 403) throw new Error("нет доступа");
    if (resp.status === 404) throw new Error("файл не найден");
    throw new Error("не удалось загрузить файл");
  }
  return resp.arrayBuffer();
}

function TruncatedNote({ shown, total }: { shown: number; total: number }) {
  if (total <= shown) return null;
  return (
    <div className="border-t border-[var(--border-subtle)] px-3 py-1.5 text-xs text-[var(--fg-muted)]">
      Показаны первые {shown.toLocaleString()} из {total.toLocaleString()} строк.
      Полный файл — кнопкой «Скачать».
    </div>
  );
}

/** CSV/TSV → таблица (парсинг через papaparse, грузится по требованию). */
export function CsvView({ text, delimiter }: { text: string; delimiter: string }) {
  const [rows, setRows] = useState<string[][] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const Papa = (await import("papaparse")).default;
        const res = Papa.parse<string[]>(text, {
          delimiter,
          skipEmptyLines: true,
        });
        if (!cancelled) setRows(res.data as string[][]);
      } catch (e) {
        if (!cancelled) setErr((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [text, delimiter]);

  if (err) return <Centered>Не удалось разобрать таблицу: {err}</Centered>;
  if (!rows) return <Centered>Разбираем таблицу…</Centered>;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <SheetTable rows={rows.slice(0, MAX_TABLE_ROWS)} />
      <TruncatedNote shown={Math.min(rows.length, MAX_TABLE_ROWS)} total={rows.length} />
    </div>
  );
}

/** XLSX/XLS → вкладки листов + таблица (SheetJS, грузится по требованию). */
export function XlsxView({ url }: { url: string }) {
  const [names, setNames] = useState<string[]>([]);
  const [active, setActive] = useState(0);
  const [rows, setRows] = useState<(string | number)[][]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const wbRef = useRef<unknown>(null);
  const xlsxRef = useRef<typeof import("xlsx") | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const XLSX = await import("xlsx");
        xlsxRef.current = XLSX;
        const buf = await fetchBytes(url);
        const wb = XLSX.read(buf, { type: "array" });
        if (cancelled) return;
        if (!wb.SheetNames.length) {
          setErr("в книге нет листов");
          return;
        }
        wbRef.current = wb;
        setNames(wb.SheetNames);
        setActive(0);
      } catch (e) {
        if (!cancelled) setErr((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url]);

  useEffect(() => {
    const XLSX = xlsxRef.current;
    const wb = wbRef.current as { Sheets: Record<string, unknown> } | null;
    if (!XLSX || !wb || !names[active]) return;
    const ws = wb.Sheets[names[active]];
    const data = XLSX.utils.sheet_to_json(ws as never, {
      header: 1,
      blankrows: false,
      defval: "",
    }) as (string | number)[][];
    setRows(data);
  }, [active, names]);

  if (err) return <Centered>Не удалось открыть таблицу: {err}</Centered>;
  if (loading) return <Centered>Открываем таблицу…</Centered>;
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {names.length > 1 && (
        <div className="flex gap-1 overflow-x-auto border-b border-[var(--border-subtle)] px-2 py-1">
          {names.map((n, i) => (
            <button
              key={n}
              onClick={() => setActive(i)}
              className={`shrink-0 rounded px-2 py-1 text-xs ${
                i === active
                  ? "bg-[var(--bg-hover)] text-[var(--fg-primary)]"
                  : "text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]"
              }`}
            >
              {n}
            </button>
          ))}
        </div>
      )}
      <SheetTable rows={rows.slice(0, MAX_TABLE_ROWS)} />
      <TruncatedNote shown={Math.min(rows.length, MAX_TABLE_ROWS)} total={rows.length} />
    </div>
  );
}

/** DOCX → HTML через mammoth, показываем в sandbox-iframe (без скриптов). */
export function DocxView({ url }: { url: string }) {
  const [html, setHtml] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mammoth = await import("mammoth");
        const buf = await fetchBytes(url);
        const res = await mammoth.convertToHtml({ arrayBuffer: buf });
        if (!cancelled) setHtml(res.value || "<p><em>Пустой документ</em></p>");
      } catch (e) {
        if (!cancelled) setErr((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (err) return <Centered>Не удалось открыть документ: {err}</Centered>;
  if (html == null) return <Centered>Открываем документ…</Centered>;
  const doc = `<!doctype html><html><head><meta charset="utf-8"><style>
    body{font-family:system-ui,'Segoe UI',Roboto,sans-serif;color:#1a1a1a;background:#fff;padding:28px;line-height:1.65;max-width:820px;margin:0 auto}
    img{max-width:100%}h1,h2,h3{line-height:1.3}
    table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #ccc;padding:4px 8px}
  </style></head><body>${html}</body></html>`;
  return (
    <iframe
      sandbox=""
      title="Документ"
      className="min-h-0 w-full flex-1 bg-white"
      srcDoc={doc}
    />
  );
}

async function fetchDocHtml(url: string): Promise<string> {
  const resp = await fetch(url, { credentials: "include" });
  let data: { html?: string; detail?: unknown } | null = null;
  try {
    data = (await resp.json()) as { html?: string; detail?: unknown };
  } catch {
    data = null;
  }
  if (!resp.ok) {
    const detail = data?.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : "не удалось открыть документ Word";
    throw new Error(msg);
  }
  if (!data?.html) throw new Error("пустой ответ сервера");
  return data.html;
}

/** Старый .doc: HTML с сервера в sandbox-iframe (как DOCX/mammoth). */
export function DocHtmlView({
  url,
  onDownload,
}: {
  url: string;
  onDownload: () => void;
}) {
  const [html, setHtml] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!url) {
      setErr("нет адреса превью");
      return;
    }
    (async () => {
      try {
        const body = await fetchDocHtml(url);
        if (!cancelled) setHtml(body);
      } catch (e) {
        if (!cancelled) setErr((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (err) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
        <p className="text-sm text-[var(--fg-muted)]">
          Не удалось открыть документ: {err}
        </p>
        <button
          onClick={onDownload}
          className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[var(--bg-canvas)] transition-opacity hover:opacity-90"
        >
          Скачать
        </button>
      </div>
    );
  }
  if (html == null) return <Centered>Открываем документ…</Centered>;
  const doc = `<!doctype html><html><head><meta charset="utf-8"><style>
    body{font-family:system-ui,'Segoe UI',Roboto,sans-serif;color:#1a1a1a;background:#fff;padding:28px;line-height:1.65;max-width:820px;margin:0 auto}
    img{max-width:100%}h1,h2,h3{line-height:1.3}
    table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #ccc;padding:4px 8px}
  </style></head><body>${html}</body></html>`;
  return (
    <iframe
      sandbox=""
      title="Документ"
      className="min-h-0 w-full flex-1 bg-white"
      srcDoc={doc}
    />
  );
}
