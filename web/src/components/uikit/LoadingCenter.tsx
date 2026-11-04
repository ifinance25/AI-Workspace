/** Индикатор ожидания в стиле UIKit: полоска сверху (как Google) + кольцо по центру. */

import { useEffect, useLayoutEffect, useState } from "react";
import { useLocation } from "react-router-dom";

type LoadingCenterProps = {
  label?: string;
  /** Центр в доступной области (экран, колонка, превью файла). */
  fill?: boolean;
  /** Верхняя полоска (viewport). По умолчанию выключена: полоска на всех экранах через UIKitRouteProgress. */
  topProgress?: boolean;
  className?: string;
};

type TopProgressPhase = "run" | "done" | "gone";

export function UIKitSpinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`uikit-spinner inline-block shrink-0 ${className}`.trim()}
      aria-hidden="true"
    />
  );
}

type UIKitTopProgressProps = {
  label?: string;
  /**
   * undefined — одноразовый цикл: indeterminate до готовности DOM, затем 100% и скрытие.
   * true/false — indeterminate пока true; при false полоска доходит до конца и скрывается.
   */
  active?: boolean;
  onFinished?: () => void;
};

function scheduleDomReady(onReady: () => void) {
  let id1 = 0;
  let id2 = 0;
  id1 = requestAnimationFrame(() => {
    id2 = requestAnimationFrame(onReady);
  });
  return () => {
    cancelAnimationFrame(id1);
    cancelAnimationFrame(id2);
  };
}

/** Тонкая полоска прогресса у верхнего края экрана. */
export function UIKitTopProgress({ label = "Загрузка", active, onFinished }: UIKitTopProgressProps) {
  const [phase, setPhase] = useState<TopProgressPhase>("run");

  useLayoutEffect(() => {
    if (active !== undefined) return;
    return scheduleDomReady(() => setPhase("done"));
  }, [active]);

  useEffect(() => {
    if (active === undefined) return;
    if (active) setPhase("run");
    else setPhase("done");
  }, [active]);

  useEffect(() => {
    if (phase !== "done") return;
    const t = window.setTimeout(() => setPhase("gone"), 380);
    return () => window.clearTimeout(t);
  }, [phase]);

  useEffect(() => {
    if (phase !== "gone") return;
    onFinished?.();
  }, [phase, onFinished]);

  if (phase === "gone") return null;

  const indeterminate = phase === "run";
  const rootClass = indeterminate
    ? "uikit-top-progress uikit-top-progress--indeterminate"
    : "uikit-top-progress uikit-top-progress--complete";

  return (
    <div
      className={rootClass}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : 100}
      aria-label={label}
      aria-busy={indeterminate}
    >
      <span className="uikit-top-progress__bar" aria-hidden="true" />
    </div>
  );
}

/** Полоска при каждой смене маршрута: завершается после отрисовки DOM страницы. */
export function UIKitRouteProgress() {
  const location = useLocation();
  return <UIKitTopProgress key={location.key} label="Загрузка страницы" />;
}

export default function LoadingCenter({
  label = "Загрузка…",
  fill = true,
  topProgress = false,
  className = "",
}: LoadingCenterProps) {
  const layout = fill
    ? "flex min-h-0 flex-1 items-center justify-center p-6"
    : "flex items-center justify-center py-10";
  return (
    <>
      {topProgress ? <UIKitTopProgress label={label} /> : null}
      <div
        role="status"
        aria-live="polite"
        aria-busy="true"
        aria-label={label}
        className={`${layout} ${className}`.trim()}
      >
        <div className="flex flex-col items-center gap-3 text-center">
          <UIKitSpinner />
          {label ? (
            <span className="max-w-xs text-sm text-[var(--fg-muted)]">{label}</span>
          ) : null}
        </div>
      </div>
    </>
  );
}
