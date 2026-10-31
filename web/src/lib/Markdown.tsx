import { Children, isValidElement, type ComponentProps, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import rehypeSanitize from "rehype-sanitize";
import TaskDraftCard, { parseTaskDraft } from "@/components/chat/TaskDraftCard";

type RehypePlugins = ComponentProps<typeof ReactMarkdown>["rehypePlugins"];

function plainText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(plainText).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return plainText(node.props.children);
  return "";
}

/** Блок ```pm-task от чата: карточка с кнопкой «Создать». Не разобрался как JSON: обычный код. */
function Pre({ children }: { children?: ReactNode }) {
  const code = Children.toArray(children)[0];
  if (isValidElement<{ className?: string; children?: ReactNode }>(code)) {
    if (/\blanguage-pm-task\b/.test(code.props.className ?? "")) {
      const draft = parseTaskDraft(plainText(code.props.children));
      if (draft) return <TaskDraftCard draft={draft} />;
    }
  }
  return <pre>{children}</pre>;
}

/**
 * Единый markdown-рендер для ответов Claude и просмотра документации.
 * remark-gfm: таблицы, списки задач, ~~strike~~, автоссылки.
 * rehype-sanitize: вырезает опасный HTML (XSS), запускается ПОСЛЕ
 * highlight, чтобы пропустить только безопасные className подсветки.
 * Базовый вес — нормальный; жирным только реальный **bold** (см. typography).
 */
export function Markdown({
  children,
  detect = false,
}: {
  children: string;
  // detect: включить авто-определение языка highlight.js для блоков кода без
  // явного языка (нужно файловому просмотру, где расширение не всегда известно).
  detect?: boolean;
}) {
  const rehypePlugins: RehypePlugins = detect
    ? [[rehypeHighlight, { detect: true }], rehypeSanitize]
    : [rehypeHighlight, rehypeSanitize];
  return (
    <div className="markdown-body text-base leading-[1.7] text-[var(--fg-primary)]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={rehypePlugins}
        components={{ pre: Pre }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
