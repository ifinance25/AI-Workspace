// Клиент API вкладки «Бриф»: версии брифа проекта офиса. Текст идёт JSON через
// officeRequest, файл multipart отдельным fetch.
import { apiUrl } from "@/api/base";
import { ApiError, AUTH_UNAUTHORIZED_EVENT } from "@/api/client";
import { officeRequest } from "@/components/office/officeApi";

export interface BriefVersion {
  id: number;
  number: number;
  status: string;
  source: string;
  created_at: string;
}

export interface BriefParagraph {
  id: string;
  text: string;
}

export interface BriefVersionFull extends BriefVersion {
  markdown: string;
  paragraphs: BriefParagraph[];
}

export interface BriefSaveResult {
  version: BriefVersion;
  created: boolean;
}

export const ACCEPTED_BRIEF_FILES = ".md,.txt,.docx";

// Текст ошибки для человека: поле detail из ответа сервера, иначе сообщение как есть.
export function errorText(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  const start = message.indexOf("{");
  if (start >= 0) {
    try {
      const detail = JSON.parse(message.slice(start)).detail;
      if (typeof detail === "string") return detail;
    } catch {
      // не JSON: отдаём сообщение целиком
    }
  }
  return message;
}

const base = (projectId: number) => `/api/office/projects/${projectId}/brief`;

export const briefApi = {
  listVersions(projectId: number) {
    return officeRequest<BriefVersion[]>("GET", `${base(projectId)}/versions`);
  },
  getVersion(projectId: number, number: number) {
    return officeRequest<BriefVersionFull>("GET", `${base(projectId)}/versions/${number}`);
  },
  saveText(projectId: number, text: string) {
    return officeRequest<BriefSaveResult>("POST", base(projectId), { text });
  },
  async uploadFile(projectId: number, file: File): Promise<BriefSaveResult> {
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(apiUrl(`${base(projectId)}/file`), {
      method: "POST",
      credentials: "include",
      body: form,
    });
    if (!resp.ok) {
      if (resp.status === 401 && typeof window !== "undefined") {
        window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
      }
      const text = await resp.text();
      throw new ApiError(resp.status, `${resp.status} ${resp.statusText}: ${text}`);
    }
    return resp.json() as Promise<BriefSaveResult>;
  },
};
