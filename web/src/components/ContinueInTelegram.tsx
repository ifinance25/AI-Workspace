import { ReplyIcon } from "@/components/icons";

export function ContinueInTelegram({
  botUsername,
  sessionUuid,
  canContinue = true,
}: {
  botUsername?: string;
  sessionUuid: string;
  // Скрываем у локальных (логин/пароль) юзеров: для них deeplink-owner-check
  // не совпадёт и кнопка вела бы в тупик (флаг из /api/me).
  canContinue?: boolean;
}) {
  if (!botUsername || !canContinue) return null;
  const href = `https://t.me/${botUsername}?start=continue_${encodeURIComponent(
    sessionUuid,
  )}`;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="icon-btn flex h-11 w-11 shrink-0 items-center justify-center gap-2 rounded-xl text-sm text-[var(--fg-secondary)] transition-colors hover:bg-[var(--bg-hover)] hover:text-[var(--fg-primary)] lg:h-9 lg:w-auto lg:px-2.5"
      title="Продолжить эту сессию в Telegram"
      aria-label="Продолжить в Telegram"
    >
      <ReplyIcon size={18} />
      <span className="sr-only lg:not-sr-only">В Telegram</span>
    </a>
  );
}
