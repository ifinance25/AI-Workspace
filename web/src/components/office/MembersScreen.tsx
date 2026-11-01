// Экран «Команда»: кто в проекте и в какой роли. Менять может менеджер проекта.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import LoadingCenter from "@/components/uikit/LoadingCenter";
import { membersApi, type TeamInfo } from "@/components/office/membersApi";
import { errorText } from "@/components/runs/runsApi";

const FIELD =
  "rounded-lg border border-[var(--border-subtle)] bg-transparent px-2 py-1.5 text-sm";
const BUTTON =
  "rounded-lg border border-[var(--border-subtle)] px-3 py-1.5 text-sm hover:bg-[var(--bg-hover)] disabled:opacity-50";

export default function MembersScreen({ projectId }: { projectId: number }) {
  const [team, setTeam] = useState<TeamInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState("");
  const [role, setRole] = useState("tester");

  const load = useCallback(async () => {
    try {
      setTeam(await membersApi.team(projectId));
      setError(null);
    } catch (err) {
      setError(errorText(err));
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  if (!team) {
    return error ? (
      <p role="alert" className="text-sm text-[var(--danger,#b42318)]">
        {error}
      </p>
    ) : (
      <LoadingCenter />
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Команда проекта</h1>
        <Link to={`/office/${projectId}/runs`} className="text-sm underline">
          Прогоны
        </Link>
      </div>
      {error && (
        <p role="alert" className="text-sm text-[var(--danger,#b42318)]">
          {error}
        </p>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[var(--fg-secondary)]">
            <th className="py-2 pr-3 font-medium">Логин</th>
            <th className="py-2 pr-3 font-medium">Роль</th>
            <th className="py-2" />
          </tr>
        </thead>
        <tbody>
          {team.members.map((m) => (
            <tr key={m.user_id} className="border-t border-[var(--border-subtle)]">
              <td className="py-2 pr-3">{m.username}</td>
              <td className="py-2 pr-3">
                {team.can_manage ? (
                  <select
                    aria-label={`Роль: ${m.username}`}
                    className={FIELD}
                    value={m.role}
                    disabled={busy}
                    onChange={(e) => void run(() => membersApi.setRole(projectId, m.user_id, e.target.value))}
                  >
                    {team.roles.map((r) => (
                      <option key={r.key} value={r.key}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  m.label
                )}
              </td>
              <td className="py-2 text-right">
                {team.can_manage && (
                  <button
                    type="button"
                    className={BUTTON}
                    disabled={busy}
                    onClick={() => {
                      if (window.confirm(`Убрать ${m.username} из проекта?`)) {
                        void run(() => membersApi.remove(projectId, m.user_id));
                      }
                    }}
                  >
                    Убрать
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {team.can_manage && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const name = username.trim();
            if (!name) return;
            void run(async () => {
              await membersApi.add(projectId, name, role);
              setUsername("");
            });
          }}
        >
          <label className="text-sm">
            <span className="mb-1 block text-[var(--fg-secondary)]">Логин учётки</span>
            <input
              className={FIELD}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-[var(--fg-secondary)]">Роль</span>
            <select className={FIELD} value={role} onChange={(e) => setRole(e.target.value)}>
              {team.roles.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className={BUTTON} disabled={busy || !username.trim()}>
            Добавить
          </button>
          <p className="basis-full text-xs text-[var(--fg-secondary)]">
            Учётку создаёт администратор в разделе «Администрирование». Здесь она входит в проект.
          </p>
        </form>
      )}
    </div>
  );
}
