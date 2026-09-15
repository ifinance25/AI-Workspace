import { Markdown } from "@/lib/Markdown";
import { CsvView, DocxView, XlsxView } from "@/components/files/RichViewers";
import type { FileContent } from "@/lib/types";

const EXT_LANG: Record<string, string> = {
  ts: "typescript", tsx: "tsx", js: "javascript", jsx: "jsx",
  py: "python", json: "json", md: "markdown", css: "css", scss: "scss",
  html: "html", xml: "xml", sh: "bash", bash: "bash", zsh: "bash",
  yml: "yaml", yaml: "yaml", toml: "toml", ini: "ini", conf: "ini", cfg: "ini",
  sql: "sql", go: "go", rs: "rust", rb: "ruby", php: "php", java: "java",
  kt: "kotlin", swift: "swift", c: "c", h: "c", cpp: "cpp", hpp: "cpp",
  cs: "csharp", dockerfile: "dockerfile", env: "bash", txt: "",
};

// SVG НЕ здесь: его рендерим в sandbox-iframe (по содержимому), а не <img> с
// inline-URL — image/svg+xml исполняет скрипты при прямом открытии (XSS).
const IMAGE_EXTS = new Set([
  "png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "avif",
]);

// Тяжёлые форматы (docx/xlsx) грузятся целиком в браузер — выше лимита
// показываем «Скачать», чтобы не подвесить вкладку.
export const MAX_RICH_BYTES = 12 * 1024 * 1024;

export type FileViewerKind =
  | "image"
  | "pdf"
  | "docx"
  | "xlsx"
  | "csv"
  | "html"
  | "markdown"
  | "text"
  | "download";

export function fileExt(rel: string): string {
  return rel.split(".").pop()?.toLowerCase() ?? "";
}

/** Какой viewer открыть по расширению и размеру. Тестируется отдельно от React. */
export function fileViewerKind(
  rel: string,
  opts: { sizeBytes?: number; binary?: boolean; tooLarge?: boolean } = {},
): FileViewerKind {
  const e = fileExt(rel);
  const tooBig = (opts.sizeBytes ?? 0) > MAX_RICH_BYTES;
  if (IMAGE_EXTS.has(e)) return "image";
  if (e === "pdf") return "pdf";
  if (e === "docx") return tooBig ? "download" : "docx";
  if (e === "xlsx" || e === "xls" || e === "xlsm") return tooBig ? "download" : "xlsx";
  if (opts.binary || opts.tooLarge) return "download";
  if (e === "csv" || e === "tsv") return "csv";
  if (e === "html" || e === "htm" || e === "svg") return "html";
  if (e === "md" || e === "markdown" || e === "mdx") return "markdown";
  return "text";
}

function extLang(rel: string): string {
  return EXT_LANG[fileExt(rel)] ?? "";
}

// Оборачиваем содержимое в fenced-блок длиннее любой внутренней серии бэктиков,
// чтобы текст с ``` не ломал разметку. Подсветка — существующий rehype-highlight.
// Длину самой длинной серии бэктиков считаем за ОДИН проход (раньше был
// while(includes) → O(n²) и подвешивал вкладку на больших файлах с бэктиками).
function fence(content: string, lang: string): string {
  const runs = content.match(/`+/g);
  const longest = runs ? runs.reduce((m, r) => Math.max(m, r.length), 0) : 0;
  const ticks = "`".repeat(Math.max(3, longest + 1));
  return `${ticks}${lang}\n${content}\n${ticks}`;
}

function DownloadFallback({
  label,
  onDownload,
}: {
  label: string;
  onDownload: () => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
      <p className="text-sm text-[var(--fg-muted)]">{label}</p>
      <button
        onClick={onDownload}
        className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-[var(--bg-canvas)] transition-opacity hover:opacity-90"
      >
        Скачать
      </button>
    </div>
  );
}

export default function FileViewer({
  file,
  inlineUrl,
  downloadUrl,
  onDownload,
}: {
  file: FileContent;
  /** URL для inline-показа (картинка/PDF). */
  inlineUrl: string;
  /** URL для скачивания/чтения байтов (docx/xlsx). */
  downloadUrl: string;
  onDownload: () => void;
}) {
  const kind = fileViewerKind(file.rel, {
    sizeBytes: file.size_bytes,
    binary: file.binary,
    tooLarge: file.too_large,
  });
  const e = fileExt(file.rel);

  if (kind === "image") {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-[var(--bg-canvas)] p-3">
        <img
          src={inlineUrl}
          alt={file.rel}
          className="max-h-full max-w-full object-contain"
        />
      </div>
    );
  }

  // PDF — встроенный просмотрщик браузера + страховка «открыть в новой вкладке»
  // (на случай, если встроенный просмотр PDF где-то заблокирован политиками).
  if (kind === "pdf") {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center justify-end gap-3 border-b border-[var(--border-subtle)] px-3 py-1.5 text-xs">
          <a
            href={inlineUrl}
            target="_blank"
            rel="noreferrer"
            className="text-[var(--accent)] hover:opacity-90"
          >
            Открыть в новой вкладке
          </a>
        </div>
        <iframe
          src={inlineUrl}
          title={file.rel}
          className="min-h-0 w-full flex-1 bg-white"
        />
      </div>
    );
  }

  if (kind === "docx") {
    return <DocxView url={downloadUrl} />;
  }
  if (kind === "xlsx") {
    return <XlsxView url={downloadUrl} />;
  }

  if (kind === "download") {
    const label =
      e === "docx"
        ? "Документ слишком большой для просмотра"
        : e === "xlsx" || e === "xls" || e === "xlsm"
          ? "Таблица слишком большая для просмотра"
          : file.binary
            ? "Бинарный файл"
            : "Файл слишком большой для просмотра";
    return <DownloadFallback label={label} onDownload={onDownload} />;
  }

  if (kind === "csv") {
    return <CsvView text={file.content} delimiter={e === "tsv" ? "\t" : ","} />;
  }

  // HTML / SVG → безопасный sandbox-iframe (без скриптов и same-origin).
  if (e === "html" || e === "htm" || e === "svg") {
    return (
      <iframe
        sandbox=""
        title={file.rel}
        className="min-h-0 w-full flex-1 bg-white"
        srcDoc={file.content}
      />
    );
  }

  // Markdown — рендерим как разметку, а не «стену кода».
  if (e === "md" || e === "markdown" || e === "mdx") {
    return (
      <div className="file-view min-h-0 flex-1 overflow-auto p-4">
        <Markdown>{file.content}</Markdown>
      </div>
    );
  }

  // Остальной текст/код — подсветка в fenced-блоке.
  return (
    <div className="file-view min-h-0 flex-1 overflow-auto p-3">
      {/* detect: для файлов без узнаваемого расширения (Caddyfile, .conf и т.п.)
          highlight.js сам определит язык — подсветка вместо «стены решёток». */}
      <Markdown detect>{fence(file.content, extLang(file.rel))}</Markdown>
    </div>
  );
}
