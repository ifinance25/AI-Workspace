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
  listProjects() {
    return officeRequest<OfficeProject[]>("GET", "/api/office/projects");
  },
  getProject(id: number) {
    return officeRequest<OfficeProject>("GET", `/api/office/projects/${id}`);
  },
};
