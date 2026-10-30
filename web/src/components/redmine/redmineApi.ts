// Клиент четырёх вызовов зеркала. Ключ API сюда не входит и в запрос не кладётся.
import { officeRequest } from "@/components/office/officeApi";

export interface RedminePerson {
  user_id: number | null;
  login: string;
  name: string;
}

export interface RedmineIssue {
  id: number;
  subject: string;
  description: string;
  status: { id: string; name: string };
  author: RedminePerson | null;
  assignee: RedminePerson | null;
  start_date: string | null;
  due_date: string | null;
  comments: Array<{
    id: number | null;
    text: string;
    at: string;
    author: RedminePerson | null;
  }>;
  status_history: Array<{ at: string; old: string; new: string }>;
  assignee_history: Array<{ at: string; old: string; new: string }>;
  ftt_section: string;
  cycle_hours: number | null;
  type?: string;
  environment?: string;
}

export interface RedmineView {
  connected: boolean;
  updated: boolean;
  message: string;
  issues: RedmineIssue[];
  interval_minutes: number;
  synced_at: string | null;
  next_sync_at: string | null;
  lookups?: RedmineLookups;
}

export interface RedmineLookups {
  types: string[];
  environments: string[];
  ftt_sections: string[];
  statuses: Array<{ id: string; name: string }>;
  authors: string[];
  assignees: string[];
  people_by_name?: Record<string, number>;
}

export interface RedmineIssueResult {
  updated: boolean;
  message?: string;
  issue: RedmineIssue;
}

export const redmineApi = {
  fetchMirror(projectId: number) {
    return officeRequest<RedmineView>("GET", `/api/office/projects/${projectId}/redmine`);
  },
  loadProject(projectId: number, redmineProject: string) {
    return officeRequest<RedmineView>(
      "POST",
      `/api/office/projects/${projectId}/redmine/load`,
      { redmine_project: redmineProject },
    );
  },
  createIssue(
    projectId: number,
    body: {
      request_key: string;
      redmine_project: string;
      subject: string;
      description?: string;
      status_id?: string;
      assigned_to_id?: number;
      start_date?: string | null;
      due_date?: string | null;
      notes?: string;
    },
  ) {
    return officeRequest<RedmineIssueResult>(
      "POST",
      `/api/office/projects/${projectId}/redmine/issues`,
      body,
    );
  },
  updateIssue(
    projectId: number,
    issueId: number,
    body: {
      subject?: string;
      description?: string;
      status_id?: string;
      assigned_to_id?: number;
      start_date?: string | null;
      due_date?: string | null;
      notes?: string;
    },
  ) {
    return officeRequest<RedmineIssueResult>(
      "PUT",
      `/api/office/projects/${projectId}/redmine/issues/${issueId}`,
      body,
    );
  },
};
