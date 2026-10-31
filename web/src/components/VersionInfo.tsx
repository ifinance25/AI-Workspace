import { useEffect, useState } from "react";
import {
  fetchServerVersion,
  formatStamp,
  UI_VERSION,
  type ServerVersion,
} from "@/lib/version";

/** Версия PM Workspace: что собрано в интерфейсе и что запущено на сервере. */
export default function VersionInfo() {
  const [server, setServer] = useState<ServerVersion | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchServerVersion()
      .then((v) => {
        if (!cancelled) setServer(v);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const mismatch = server !== null && server.commit !== UI_VERSION.commit;
  const uiDate = formatStamp(UI_VERSION.date);
  const serverDate = server ? formatStamp(server.committed_at) : "";
  const started = server ? formatStamp(server.started_at) : "";

  return (
    <div
      className="mt-auto hidden border-t border-[var(--border-subtle)] px-3 pt-3 text-xs leading-5 text-[var(--fg-muted)] md:block"
      data-testid="version-info"
    >
      <div className="font-medium text-[var(--fg-secondary)]">PM Workspace</div>
      <div>
        Сервер: {server ? server.commit : failed ? "нет данных" : "…"}
        {serverDate ? `, ${serverDate}` : ""}
      </div>
      {started && <div>Запущен: {started}</div>}
      <div>
        Интерфейс: {UI_VERSION.commit}
        {uiDate ? `, ${uiDate}` : ""}
      </div>
      {mismatch && (
        <div className="mt-1 text-amber-500">
          Версии разные: обновите страницу (Cmd+Shift+R).
        </div>
      )}
    </div>
  );
}
