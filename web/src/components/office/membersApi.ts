// Клиент состава команды проекта офиса.
import { officeRequest } from "@/components/office/officeApi";

export interface TeamMember {
  user_id: number;
  username: string;
  role: string;
  label: string;
  added_at: string;
}

export interface TeamInfo {
  members: TeamMember[];
  can_manage: boolean;
  roles: Array<{ key: string; label: string }>;
}

const base = (projectId: number) => `/api/office/projects/${projectId}/members`;

export const membersApi = {
  team: (projectId: number) => officeRequest<TeamInfo>("GET", base(projectId)),
  add: (projectId: number, username: string, role: string) =>
    officeRequest<{ user_id: number; role: string }>("POST", base(projectId), { username, role }),
  setRole: (projectId: number, userId: number, role: string) =>
    officeRequest<{ user_id: number; role: string }>("PUT", `${base(projectId)}/${userId}`, {
      role,
    }),
  remove: (projectId: number, userId: number) =>
    officeRequest<void>("DELETE", `${base(projectId)}/${userId}`),
};
