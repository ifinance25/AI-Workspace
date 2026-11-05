// Просмотр снимков находки: стрелки, точки, заголовок документа текущего снимка.
import { useEffect } from "react";

export interface Shot {
  src: string;
  doc: string;
  page?: number | null;
  quote?: string;
}

interface Props {
  shots: Shot[];
  index: number;
  onIndex: (next: number) => void;
  onClose: () => void;
  onOpenPdf?: (doc: string, page: number | null | undefined) => void;
}

const ARROW =
  "absolute top-1/2 -translate-y-1/2 rounded-full bg-black/60 px-4 py-3 text-2xl leading-none text-white hover:bg-black/80 disabled:opacity-30";

export default function ShotCarousel({ shots, index, onIndex, onClose, onOpenPdf }: Props) {
  const last = shots.length - 1;
  const current = shots[index];

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      else if (event.key === "ArrowLeft") onIndex(Math.max(0, index - 1));
      else if (event.key === "ArrowRight") onIndex(Math.min(last, index + 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, last, onIndex, onClose]);

  if (!current) return null;
  const title = current.page ? `${current.doc}, стр. ${current.page}` : current.doc;

  return (
    <div
      role="dialog"
      aria-modal
      aria-label="Просмотр снимков"
      className="fixed inset-0 z-50 flex flex-col items-center bg-black/80 p-4"
      onClick={onClose}
    >
      <div
        className="mb-3 flex w-full max-w-5xl items-start justify-between gap-3 text-white"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="min-w-0">
          <p className="truncate text-base font-semibold" data-testid="shot-title">
            {title}
          </p>
          {current.quote && <p className="line-clamp-2 text-sm opacity-80">«{current.quote}»</p>}
        </div>
        <div className="flex shrink-0 items-center gap-3 text-sm">
          {onOpenPdf && current.page ? (
            <button
              type="button"
              className="rounded-lg bg-black/50 px-3 py-1.5 underline"
              onClick={(event) => {
                event.stopPropagation();
                onOpenPdf(current.doc, current.page);
                onClose();
              }}
            >
              Открыть PDF на странице {current.page}
            </button>
          ) : null}
          <span aria-live="polite">
            {index + 1} / {shots.length}
          </span>
          <button type="button" onClick={onClose} className="rounded-lg bg-black/50 px-3 py-1.5">
            Закрыть
          </button>
        </div>
      </div>
      <div className="relative flex min-h-0 w-full max-w-5xl flex-1 items-center justify-center">
        <img
          key={current.src}
          src={current.src}
          alt={title}
          className="max-h-full max-w-full rounded shadow-lg"
          onClick={(event) => event.stopPropagation()}
        />
        {last > 0 && (
          <>
            <button
              type="button"
              aria-label="Предыдущий снимок"
              disabled={index === 0}
              className={`${ARROW} left-0`}
              onClick={(event) => {
                event.stopPropagation();
                onIndex(index - 1);
              }}
            >
              ‹
            </button>
            <button
              type="button"
              aria-label="Следующий снимок"
              disabled={index === last}
              className={`${ARROW} right-0`}
              onClick={(event) => {
                event.stopPropagation();
                onIndex(index + 1);
              }}
            >
              ›
            </button>
          </>
        )}
      </div>
      {last > 0 && (
        <div
          className="mt-3 flex flex-wrap justify-center gap-2"
          onClick={(event) => event.stopPropagation()}
        >
          {shots.map((shot, i) => (
            <button
              key={`${shot.src}-${i}`}
              type="button"
              aria-label={`Снимок ${i + 1} из ${shots.length}: ${shot.doc}`}
              aria-current={i === index}
              className={`h-2.5 w-2.5 rounded-full ${i === index ? "bg-white" : "bg-white/40 hover:bg-white/70"}`}
              onClick={() => onIndex(i)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
