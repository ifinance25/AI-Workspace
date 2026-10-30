// Клиент API паспорта (граница project): создание, предложение типа, смена типа.
import { officeRequest, type OfficeProject } from "@/components/office/officeApi";

export const WORK_KINDS: Record<string, string> = {
  site: "Сайт",
  web_platform: "Веб-платформа",
  mobile_app: "Мобильное приложение",
};
export const NATURES: Record<string, string> = { custom: "Заказ", product: "Продукт" };
export const TYPES: Record<string, string> = { small: "Маленький", large: "Крупный" };

export interface PassportInput {
  name: string;
  work_kind: string;
  nature: string;
  description: string;
  project_type: string;
  request_key: string;
}

export interface TypeSuggestion {
  project_type: string;
  reason: string;
}

export const passportApi = {
  createProject(body: PassportInput) {
    return officeRequest<OfficeProject>("POST", "/api/office/projects", body);
  },
  suggestType(p: { work_kind: string; nature: string; description: string }) {
    return officeRequest<TypeSuggestion>("POST", "/api/office/type-suggestion", p);
  },
  setType(id: number, projectType: string) {
    return officeRequest<OfficeProject>("PUT", `/api/office/projects/${id}/type`, {
      project_type: projectType,
    });
  },
};
