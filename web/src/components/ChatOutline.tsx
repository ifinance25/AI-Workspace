import { useCallback, useEffect, useState } from "react";
import type { RefObject } from "react";

export interface OutlineItem {
  id: string;
  title: string;
  /** Краткое описание: продолжение вопроса или начало ответа Claude. */
  preview?: string;
}

const MAX_TITLE = 70;
const MAX_PREVIEW = 170;

const clean = (t: string): string =>
  t
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[#*_`>|]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const cut = (t: string, n: number): string =>
  t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t;

/** Оглавление чата: по одной черте на каждое сообщение пользователя. */
export function buildOutline(
  bubbles: { id: string; kind: string; content: string }[],
): OutlineItem[] {
  const items: OutlineItem[] = [];
  for (let i = 0; i < bubbles.length; i++) {
    const b = bubbles[i];
    if (b.kind !== "user_message") continue;
    const lines = b.content.split("\n").map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0) continue;
    let preview = clean(lines.slice(1).join(" "));
    if (!preview) {
      // Вопрос в одну строку: показываем начало ответа Claude.
      for (let j = i + 1; j < bubbles.length; j++) {
        if (bubbles[j].kind === "user_message") break;
        if (bubbles[j].kind === "text") {
          preview = clean(bubbles[j].content);
          if (preview) break;
        }
      }
    }
    items.push({
      id: b.id,
      title: cut(clean(lines[0]) || lines[0], MAX_TITLE),
      preview: preview ? cut(preview, MAX_PREVIEW) : undefined,
    });
  }
  return items;
}

interface Props {
  items: OutlineItem[];
  scrollRef: RefObject<HTMLDivElement | null>;
}

/**
 * Навигация справа в виде чёрточек (как в ChatGPT / Codex).
 * Приглушённая чёрточка — обычная, яркая — тема, на которой сейчас экран.
 * При наведении мыши показывается заголовок темы; клик прокручивает к ней.
 */
export default function ChatOutline({ items, scrollRef }: Props) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);

  const findNode = useCallback(
    (id: string): HTMLElement | null =>
      scrollRef.current?.querySelector<HTMLElement>(
        `[data-bubble-id="${CSS.escape(id)}"]`,
      ) ?? null,
    [scrollRef],
  );

  const updateActive = useCallback(() => {
    const box = scrollRef.current;
    if (!box || items.length === 0) return;
    const line = box.getBoundingClientRect().top + box.clientHeight * 0.3;
    let current = items[0].id;
    for (const it of items) {
      const node = findNode(it.id);
      if (node && node.getBoundingClientRect().top <= line) current = it.id;
    }
    setActiveId(current);
  }, [items, scrollRef, findNode]);

  useEffect(() => {
    const box = scrollRef.current;
    if (!box) return;
    updateActive();
    box.addEventListener("scroll", updateActive, { passive: true });
    return () => box.removeEventListener("scroll", updateActive);
  }, [scrollRef, updateActive]);

  if (items.length < 2) return null;

  const goTo = (id: string) => {
    findNode(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveId(id);
  };

  return (
    <nav
      aria-label="Оглавление чата"
      className="absolute right-1 top-1/2 z-20 hidden max-h-[60%] -translate-y-1/2 flex-col items-end overflow-y-auto py-2 sm:flex"
    >
      {items.map((it) => {
        const active = it.id === activeId;
        const hovered = it.id === hoverId;
        return (
          <button
            key={it.id}
            type="button"
            onClick={() => goTo(it.id)}
            onMouseEnter={() => setHoverId(it.id)}
            onMouseLeave={() => setHoverId(null)}
            onFocus={() => setHoverId(it.id)}
            onBlur={() => setHoverId(null)}
            aria-label={it.title}
            aria-current={active ? "true" : undefined}
            className="group relative flex h-4 w-8 shrink-0 items-center justify-end pr-1.5"
          >
            {hovered && (
              <span className="pointer-events-none absolute right-8 top-1/2 z-30 w-72 -translate-y-1/2 rounded-xl bg-[var(--bg-elevated)] px-3 py-2 text-left shadow-lg ring-1 ring-[var(--border-subtle)]">
                <span className="block text-sm font-medium leading-snug text-[var(--fg-primary)]">
                  {it.title}
                </span>
                {it.preview && (
                  <span className="mt-1 line-clamp-3 block text-xs leading-snug text-[var(--fg-secondary)]">
                    {it.preview}
                  </span>
                )}
              </span>
            )}
            <span
              className={`block h-0.5 rounded-full transition-all ${
                active
                  ? "w-5 bg-[var(--accent-brand)]"
                  : "w-3 bg-[var(--fg-muted)] opacity-40 group-hover:w-4 group-hover:opacity-80"
              }`}
            />
          </button>
        );
      })}
    </nav>
  );
}
