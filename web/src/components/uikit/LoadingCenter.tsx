/** Индикатор ожидания в стиле UIKit: полоска сверху (как Google) + кольцо по центру. */

type LoadingCenterProps = {
  label?: string;
  /** Центр в доступной области (экран, колонка, превью файла). */
  fill?: boolean;
  /** Верхняя indeterminate-полоска (viewport). */
  topProgress?: boolean;
  className?: string;
};

export function UIKitSpinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`uikit-spinner inline-block shrink-0 ${className}`.trim()}
      aria-hidden="true"
    />
  );
}

/** Тонкая полоска прогресса у верхнего края экрана. */
export function UIKitTopProgress({ label = "Загрузка" }: { label?: string }) {
  return (
    <div
      className="uikit-top-progress"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      aria-busy="true"
    >
      <span className="uikit-top-progress__bar" aria-hidden="true" />
    </div>
  );
}

export default function LoadingCenter({
  label = "Загрузка…",
  fill = true,
  topProgress = true,
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
