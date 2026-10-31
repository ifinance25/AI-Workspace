import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type {
  FindingDetail,
  FindingRow,
  RunDetail,
  RunsList,
} from "@/components/runs/runsApi";

const mockRuns = vi.hoisted(() => ({
  listRuns: vi.fn(),
  getRun: vi.fn(),
  listFindings: vi.fn(),
  getFinding: vi.fn(),
  decide: vi.fn(),
  setPolicy: vi.fn(),
  importRun: vi.fn(),
  exportRun: vi.fn(),
}));
vi.mock("@/components/runs/runsApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/runs/runsApi")>();
  return { ...actual, runsApi: mockRuns };
});

import RunsScreens from "@/components/runs/RunsScreens";

const stats = {
  total: 2,
  by_status: { new: 1, confirmed: 1 },
  validated: 1,
  findings_edits_done: 1,
  edits_total: 3,
  edits_applied: 2,
  llm_agreement: 1,
  slices: {
    severity: [{ label: "средняя", total: 2, validated: 1, fixed: 1 }],
    doc: [{ label: "ПМИ1", total: 2, validated: 1, fixed: 1 }],
    category: [{ label: "Шаги", total: 2, validated: 1, fixed: 1 }],
  },
};

const run: RunDetail = {
  id: 5,
  run_key: "RUN4",
  source_kind: "doc_review",
  title: "Прогон 4",
  stand_version: null,
  imported_at: "2026-10-31T10:00:00+00:00",
  docs: [{ id: 9, name: "FTT1.pdf" }],
  stats,
};

function row(over: Partial<FindingRow> = {}): FindingRow {
  return {
    id: 11,
    gid: "R4-001",
    doc: "ПМИ1",
    category: "Шаги",
    severity_raw: "средняя",
    llm_verdict: "подтверждено",
    review_status: "new",
    lifecycle: "new",
    decision_seq: 0,
    section: "ФТТ1 п. 4.1",
    summary: "Клик без указания места",
    ...over,
  };
}

function detail(over: Partial<FindingDetail> = {}): FindingDetail {
  return {
    ...row(),
    llm_verdict_reason: "Проверено скептиком",
    why: "Причина решения",
    clauses: ["ФТТ1 п. 4.1.1"],
    scenarios: ["ПМИ1 сц. 6"],
    redmine: [118443],
    redmine_links: ["https://redmine.example/issues/118443"],
    refs: [{ label: "ФТТ1 п. 4.1.1", pdf: "FTT1.pdf", page: 3 }],
    evidence: [],
    marked: [],
    edits: [
      {
        ordinal: 1,
        edit_key: "EDIT-R4-001-01",
        doc: "ПМИ1",
        col: "act",
        place: "ПМИ1 сц. 6, действие",
        old_text: "Было",
        new_text: "Стало",
        comment: "",
        state: "proposed",
        doc_ref: "",
      },
    ],
    history: [],
    ...over,
  };
}

function lists(over: Partial<RunsList> = {}): RunsList {
  return {
    runs: [run],
    can_decide: true,
    can_manage: false,
    export_ban: "all_external",
    ...over,
  };
}

function setup(listOver: Partial<RunsList> = {}, rows = [row()], card = detail()) {
  mockRuns.listRuns.mockResolvedValue(lists(listOver));
  mockRuns.getRun.mockResolvedValue(run);
  mockRuns.listFindings.mockResolvedValue(rows);
  mockRuns.getFinding.mockResolvedValue(card);
  mockRuns.decide.mockResolvedValue({
    finding_id: 11,
    review_status: "confirmed",
    lifecycle: "confirmed",
    decision_seq: 1,
    files_stale: false,
  });
  return render(<RunsScreens projectId={3} />);
}

async function openCard() {
  fireEvent.click(await screen.findByRole("button", { name: /R4-001/ }));
  await screen.findByRole("article");
}

describe("Экран прогонов", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("показывает список и открывает карточку", async () => {
    setup();
    await openCard();
    expect(screen.getByText("Суть несоответствия")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Стало" })).toBeTruthy();
    expect(screen.getByText("Стало", { selector: "td" })).toBeTruthy();
    expect(screen.getByText("#118443").getAttribute("href")).toBe(
      "https://redmine.example/issues/118443",
    );
  });

  it("подтверждение шлёт ключ запроса и номер решения", async () => {
    setup();
    await openCard();
    fireEvent.click(screen.getByRole("button", { name: "Подтверждено" }));
    await waitFor(() => expect(mockRuns.decide).toHaveBeenCalledTimes(1));
    expect(mockRuns.decide).toHaveBeenCalledWith(
      3,
      5,
      11,
      expect.objectContaining({ action: "confirm", expected_seq: 0, request_key: "11-0-confirm" }),
    );
  });

  it("отклонение требует причину и пояснение", async () => {
    setup();
    await openCard();
    fireEvent.click(screen.getByRole("button", { name: "Отклонено" }));
    const save = screen.getByRole("button", { name: /Сохранить: Отклонено/ });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Причина отклонения"), { target: { value: "no_basis" } });
    fireEvent.change(screen.getByLabelText("Пояснение"), { target: { value: "Нет в ФТТ" } });
    expect((save as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(mockRuns.decide).toHaveBeenCalledTimes(1));
    expect(mockRuns.decide.mock.calls[0][3]).toMatchObject({
      action: "reject",
      reason_code: "no_basis",
      why: "Нет в ФТТ",
    });
  });

  it("правки внесены доступны после подтверждения и просят версию документа", async () => {
    const confirmed = detail({ review_status: "confirmed", lifecycle: "confirmed", decision_seq: 1 });
    setup({}, [row({ review_status: "confirmed", lifecycle: "confirmed", decision_seq: 1 })], confirmed);
    await openCard();
    const apply = screen.getByRole("button", { name: "Правки внесены" }) as HTMLButtonElement;
    expect(apply.disabled).toBe(false);
    expect((screen.getByRole("button", { name: "Подтверждено" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(apply);
    const save = screen.getByRole("button", { name: /Сохранить: Правки внесены/ }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Версия документа с правками"), {
      target: { value: "ПМИ1 от 02.11.2026" },
    });
    expect(save.disabled).toBe(false);
  });

  it("ошибка сервера выводится в карточке", async () => {
    setup();
    mockRuns.decide.mockRejectedValue(
      new Error('409 Conflict: {"detail":"Находку уже изменил другой проверяющий"}'),
    );
    await openCard();
    fireEvent.click(screen.getByRole("button", { name: "Подтверждено" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Находку уже изменил другой проверяющий",
    );
  });

  it("без права решения кнопок статуса нет", async () => {
    setup({ can_decide: false });
    await openCard();
    expect(screen.queryByRole("button", { name: "Подтверждено" })).toBeNull();
    expect(screen.getByText(/Статус ставят менеджер проекта/)).toBeTruthy();
  });

  it("вкладка статистики показывает оба нужных показателя", async () => {
    setup();
    fireEvent.click(await screen.findByRole("tab", { name: "Статистика" }));
    const panel = await screen.findByTestId("stats-panel");
    expect(panel.textContent).toContain("Валидация пройдена");
    expect(panel.textContent).toContain("Правки внесены в документы");
    expect(panel.textContent).toContain("2 из 3");
  });

  it("фильтр по статусу прячет лишние находки", async () => {
    setup({}, [row(), row({ id: 12, gid: "R4-002", review_status: "rejected", lifecycle: "rejected" })]);
    await screen.findByRole("button", { name: /R4-002/ });
    fireEvent.change(screen.getByLabelText("Статус"), { target: { value: "rejected" } });
    expect(screen.queryByRole("button", { name: /R4-001/ })).toBeNull();
    expect(screen.getByRole("button", { name: /R4-002/ })).toBeTruthy();
  });

  it("управление прогоном видно только менеджеру, вывоз закрыт по умолчанию", async () => {
    const view = setup();
    await screen.findByRole("tab", { name: "Карточки" });
    expect(screen.queryByText("Загрузить прогон")).toBeNull();
    view.unmount();
    vi.clearAllMocks();
    setup({ can_manage: true });
    const download = (await screen.findByText("Скачать markdown для LLM")) as HTMLButtonElement;
    expect(download.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Разрешить вывоз/));
    await waitFor(() => expect(mockRuns.setPolicy).toHaveBeenCalledWith(3, "none"));
  });
});
