import { providerLogo } from "@/components/icons";

interface Props {
  projectName: string;
  modelLabel?: string;
  modelId?: string;
}

export default function ChatEmptyState({ projectName, modelLabel, modelId }: Props) {
  return (
    <div className="flex animate-riseIn flex-col items-center px-4 pb-4 sm:px-6 sm:pb-6">
      <div className="mb-6 flex h-20 w-20 animate-iconPop items-center justify-center rounded-full bg-[var(--bg-hover)] text-[var(--fg-primary)]">
        {providerLogo(modelId, 40)}
      </div>
      <div className="font-display text-2xl font-normal tracking-tight text-[var(--fg-primary)] sm:text-3xl">{projectName}</div>
      <div className="mt-2 text-lg text-[var(--fg-muted)]">Чем я могу помочь?</div>
      {modelLabel && (
        <div className="mt-3 flex items-center gap-2 rounded-full bg-[var(--bg-hover)] px-3 py-1 text-sm text-[var(--fg-secondary)]">
          {providerLogo(modelId, 16)} {modelLabel}
        </div>
      )}
    </div>
  );
}
