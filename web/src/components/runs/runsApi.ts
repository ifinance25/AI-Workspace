// Клиент ручной валидации находок прогона. Адреса вложены в проект офиса.
import { apiUrl } from "@/api/base";
import { ApiError, AUTH_UNAUTHORIZED_EVENT } from "@/api/client";
import { officeRequest } from "@/components/office/officeApi";

export type ReviewStatus = "new" | "confirmed" | "rejected" | "needs_info";
export type DecisionAction = "confirm" | "reject" | "clarify" | "edits_applied" | "reopen";

export interface RunSummary {
  id: number;
  run_key: string;
  source_kind: string;
  title: string;
  stand_version: string | null;
  imported_at: string;
}

export interface RunsList {
  runs: RunSummary[];
  can_decide: boolean;
  can_manage: boolean;
  export_ban: "none" | "all_external";
}

export interface SliceRow {
  label: string;
  total: number;
  validated: number | null;
  fixed: number | null;
}

export interface RunStats {
  total: number;
  by_status: Partial<Record<ReviewStatus, number>>;
  reviewed: number;
  validated: number;
  pending_decision: number;
  run_can_close: boolean;
  stand_defect_total?: number;
  confirmed_stand_defects?: number;
  stand_remediation_ready?: boolean;
  findings_edits_done: number;
  edits_total: number;
  edits_applied: number;
  llm_agreement: number | null;
  slices: Record<"severity" | "doc" | "category", SliceRow[]>;
}

export interface RunDetail extends RunSummary {
  docs: Array<{ id: number; name: string }>;
  stats: RunStats;
  stand_remediation_issue_id?: number;
}

export interface FindingRow {
  id: number;
  gid: string;
  doc: string;
  category: string;
  defect_class: string;
  severity_raw: string;
  llm_verdict: string;
  review_status: ReviewStatus;
  lifecycle: string;
  decision_seq: number;
  section: string;
  summary: string;
}

export interface FindingImage {
  doc: string;
  page?: number | null;
  img?: string | null;
  pdf?: string;
  quote?: string;
  asset_id: number | null;
}

export interface FindingEdit {
  ordinal: number;
  edit_key: string;
  doc: string;
  col: string;
  place: string;
  old_text: string;
  new_text: string;
  comment: string;
  state: string;
  doc_ref: string;
}

export interface FindingHistory {
  seq: number;
  decision_key: string;
  action: string;
  review_to: string;
  lifecycle_to: string;
  reason_code: string;
  why: string;
  actor: string;
  actor_role: string;
  at: string;
}

export interface FindingDetail extends Omit<FindingRow, "summary"> {
  llm_verdict_reason: string;
  summary: string;
  why: string;
  clauses: string[];
  scenarios: string[];
  redmine: number[];
  redmine_links: string[];
  refs: Array<{ label: string; pdf: string; page: number }>;
  evidence: FindingImage[];
  marked: FindingImage[];
  edits: FindingEdit[];
  history: FindingHistory[];
}

export interface DecisionBody {
  action: DecisionAction;
  expected_seq: number;
  request_key: string;
  why?: string;
  reason_code?: string;
  doc_ref?: string;
}

export interface DecisionResult {
  finding_id: number;
  review_status: ReviewStatus;
  lifecycle: string;
  decision_seq: number;
  files_stale: boolean;
}

export interface ImportResult {
  run_id: number;
  run_key: string;
  duplicate: boolean;
  findings?: number;
  assets?: number;
}

export interface RedmineExportBody {
  api_key: string;
  request_key: string;
}

export interface RedmineExportResult {
  issue_id: number;
  issue_url: string;
  created: boolean;
}

export function errorText(err: unknown): string {
  const message = err instanceof Error ? err.message : String(err);
  const json = message.indexOf("{");
  if (json >= 0) {
    try {
      const detail = (JSON.parse(message.slice(json)) as { detail?: unknown }).detail;
      if (typeof detail === "string") return detail;
    } catch {
      // Ответ без JSON: показываем текст как есть.
    }
  }
  return message;
}

const base = (projectId: number) => `/api/office/projects/${projectId}/validation`;

export function assetUrl(projectId: number, runId: number, assetId: number, page?: number | null) {
  const url = apiUrl(`${base(projectId)}/runs/${runId}/assets/${assetId}`);
  return page ? `${url}#page=${page}` : url;
}

async function rawRequest(method: string, path: string, body?: BodyInit): Promise<Response> {
  const resp = await fetch(apiUrl(path), { method, credentials: "include", body });
  if (!resp.ok) {
    if (resp.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
    }
    const text = await resp.text();
    throw new ApiError(resp.status, `${resp.status} ${resp.statusText}: ${text}`);
  }
  return resp;
}

export const runsApi = {
  listRuns(projectId: number) {
    return officeRequest<RunsList>("GET", `${base(projectId)}/runs`);
  },
  getRun(projectId: number, runId: number) {
    return officeRequest<RunDetail>("GET", `${base(projectId)}/runs/${runId}`);
  },
  listFindings(projectId: number, runId: number) {
    return officeRequest<FindingRow[]>("GET", `${base(projectId)}/runs/${runId}/findings`);
  },
  getFinding(projectId: number, runId: number, findingId: number) {
    return officeRequest<FindingDetail>(
      "GET",
      `${base(projectId)}/runs/${runId}/findings/${findingId}`,
    );
  },
  decide(projectId: number, runId: number, findingId: number, body: DecisionBody) {
    return officeRequest<DecisionResult>(
      "POST",
      `${base(projectId)}/runs/${runId}/findings/${findingId}/decisions`,
      body,
    );
  },
  setPolicy(projectId: number, exportBan: "none" | "all_external") {
    return officeRequest<{ export_ban: string }>("PUT", `${base(projectId)}/policy`, {
      export_ban: exportBan,
    });
  },
  async importRun(projectId: number, file: File): Promise<ImportResult> {
    const resp = await rawRequest("POST", `${base(projectId)}/runs/import`, file);
    return resp.json() as Promise<ImportResult>;
  },
  async exportRun(projectId: number, runId: number): Promise<Blob> {
    const resp = await rawRequest("POST", `${base(projectId)}/runs/${runId}/export`);
    return resp.blob();
  },
  exportRedmine(projectId: number, runId: number, findingId: number, body: RedmineExportBody) {
    return officeRequest<RedmineExportResult>(
      "POST",
      `${base(projectId)}/runs/${runId}/findings/${findingId}/redmine`,
      body,
    );
  },
  exportStandRemediation(projectId: number, runId: number, body: RedmineExportBody) {
    return officeRequest<RedmineExportResult & { findings: number }>(
      "POST",
      `${base(projectId)}/runs/${runId}/redmine-stand-remediation`,
      body,
    );
  },
};
