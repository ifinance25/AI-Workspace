import { useNavigate, useParams } from "react-router-dom";
import AppShell from "@/components/AppShell";
import MembersScreen from "@/components/office/MembersScreen";

export default function MembersPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const projectId = id !== undefined && /^\d+$/.test(id) ? Number(id) : null;

  return (
    <AppShell
      activeSessionUuid={null}
      openLastChat={false}
      onSelectSession={() => navigate("/")}
      mobileHeaderTitle="Команда"
    >
      <div className="mx-auto max-w-3xl p-4 text-[var(--fg-primary)] sm:p-6">
        {projectId === null ? <p>Проект не найден</p> : <MembersScreen projectId={projectId} />}
      </div>
    </AppShell>
  );
}
