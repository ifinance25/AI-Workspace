import { officeRequest } from "@/components/office/officeApi";

export interface ServerVersion {
  commit: string;
  committed_at: string;
  started_at: string;
}

export const UI_VERSION = {
  commit: typeof __APP_COMMIT__ === "string" ? __APP_COMMIT__ : "неизвестно",
  date: typeof __APP_COMMIT_DATE__ === "string" ? __APP_COMMIT_DATE__ : "",
};

export function fetchServerVersion(): Promise<ServerVersion> {
  return officeRequest<ServerVersion>("GET", "/api/version");
}

/** «31.10.2026 10:16» в часовом поясе браузера; пусто, если даты нет или она битая. */
export function formatStamp(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
