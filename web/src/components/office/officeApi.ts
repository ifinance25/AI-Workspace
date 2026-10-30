// Клиент API проектного офиса для оболочки: список проектов и проект по id.
// Клиенты вкладок по границам (паспорт, бриф, задание) живут отдельно и могут
// переиспользовать officeRequest. Типы офиса живут здесь, lib/types.ts не трогаем.
import { apiUrl } from "@/api/base";
import { ApiError, AUTH_UNAUTHORIZED_EVENT } from "@/api/client";

export interface OfficeProject {
  id: number;
  name: string;
  work_kind: string;
  nature: string;
  description?: string;
  project_type: string;
  status: string;
  created_by?: number;
  created_at?: string;
  updated_at?: string;
}

export async function officeRequest<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const resp = await fetch(apiUrl(path), {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    // Протухшая cookie: тот же сигнал, что у основного клиента, чтобы
    // AuthProvider увёл на /login.
    if (resp.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
    }
    const text = await resp.text();
    throw new ApiError(resp.status, `${resp.status} ${resp.statusText}: ${text}`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export const officeApi = {
  // Список листается страницами (таск 02): offset и limit уходят в query.
  listProjects(page?: { offset: number; limit: number }) {
    const q = page ? `?offset=${page.offset}&limit=${page.limit}` : "";
    return officeRequest<OfficeProject[]>("GET", `/api/office/projects${q}`);
  },
  getProject(id: number) {
    return officeRequest<OfficeProject>("GET", `/api/office/projects/${id}`);
  },
  updateProject(
    id: number,
    body: Partial<Pick<OfficeProject, "name" | "work_kind" | "nature" | "description">>,
  ) {
    return officeRequest<OfficeProject>("PUT", `/api/office/projects/${id}`, body);
  },
  deleteProject(id: number) {
    return officeRequest<void>("DELETE", `/api/office/projects/${id}`);
  },
};
