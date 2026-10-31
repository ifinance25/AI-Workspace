import { PRODUCT_NAME } from "@/lib/branding";

export default function ChatEmptyState() {
  return (
    <div className="flex animate-riseIn flex-col items-center px-4 pb-4 sm:px-6 sm:pb-6">
      <div className="font-display text-2xl font-normal tracking-tight text-[var(--fg-primary)] sm:text-3xl">{PRODUCT_NAME}</div>
      <div className="mt-2 text-lg text-[var(--fg-muted)]">Чем я могу помочь?</div>
    </div>
  );
}
