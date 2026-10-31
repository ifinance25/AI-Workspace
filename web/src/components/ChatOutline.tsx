import { useCallback, useEffect, useState } from "react";
import type { RefObject } from "react";

export interface OutlineItem {
  id: string;
  title: string;
}

const MAX_TITLE = 70;

/** Оглавление чата: по одной черте на каждое сообщение пользователя. */
export function buildOutline(
  bubbles: { id: string; kind: string; content: string }[],
): OutlineItem[] {
  const items: OutlineItem[] = [];
  for (const b of bubbles) {
    if (b.kind !== "user_message") continue;
    const line = b.content.split("\n").find((l) => l.trim()) ?? "";
    const text = line.trim().replace(/\s+/g, " ");
    if (!text) continue;
    items.push({
      id: b.id,
      title: text.length > MAX_TITLE ? `${text.slice(0, MAX_TITLE - 1)}…` : text,
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
              <span className="pointer-events-none absolute right-8 top-1/2 max-w-[18rem] -translate-y-1/2 truncate whitespace-nowrap rounded-lg bg-[var(--bg-elevated)] px-2.5 py-1 text-xs text-[var(--fg-primary)] shadow-lg ring-1 ring-[var(--border-subtle)]">
                {it.title}
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
