import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import FindingCard from "@/components/runs/FindingCard";
import { openPdfInFindingCard } from "@/components/runs/findingCardTabs";
import type { FindingDetail, RunDetail } from "@/components/runs/runsApi";

const run: RunDetail = {
  id: 1,
  run_key: "RUN1",
  series_key: "s",
  import_version: 1,
  parent_run_id: null,
  source_kind: "package",
  comparison_kind: "ftt_vs_stand",
  title: "Тест",
  stand_version: null,
  started_at: null,
  imported_at: "2026-01-01",
  documents: [{ name: "ФТТ1.pdf", role: "ФТТ" }],
  stats: {
    total: 1,
    by_status: {},
    reviewed: 0,
    validated: 0,
    pending_decision: 1,
    run_can_close: false,
    findings_edits_done: 0,
    edits_total: 0,
    edits_applied: 0,
    llm_agreement: null,
    slices: { severity: [], doc: [], category: [] },
  },
  docs: [{ id: 10, name: "ФТТ1.pdf" }],
};

const finding: FindingDetail = {
  id: 5,
  gid: "F-001",
  doc: "ФТТ1.pdf",
  category: "cat",
  defect_class: "content",
  severity_raw: "major",
  llm_verdict: "agree",
  llm_verdict_reason: "причина",
  review_status: "new",
  lifecycle: "open",
  decision_seq: 0,
  section: "s",
  summary: "Краткое описание",
  why: "Обоснование",
  clauses: [],
  scenarios: [],
  redmine: [],
  redmine_links: [],
  refs: [{ label: "ФТТ1, стр. 3", pdf: "ФТТ1.pdf", page: 3 }],
  evidence: [],
  marked: [],
  edits: [],
  history: [],
};

describe("openPdfInFindingCard", () => {
  it("переключает на вкладку pdf и сохраняет страницу", () => {
    expect(openPdfInFindingCard("ФТТ1.pdf", 7)).toEqual({
      tab: "pdf",
      pdf: { name: "ФТТ1.pdf", page: 7 },
    });
    expect(openPdfInFindingCard("a.pdf", undefined).pdf.page).toBeNull();
  });
});

describe("FindingCard: история решений", () => {
  it("не дублирует похожие статус, этап и пояснение при возврате в разбор", () => {
    const reopen: FindingDetail = {
      ...finding,
      history: [
        {
          seq: 1,
          decision_key: "k1",
          action: "reopen",
          review_to: "new",
          lifecycle_to: "reopened",
          reason_code: "",
          why: "Возвращено в разбор",
          actor: "U",
          actor_role: "tester",
          at: "2026-01-02T12:00:00Z",
        },
      ],
    };
    render(
      <FindingCard projectId={1} run={run} finding={reopen} canDecide={false} onDecided={() => {}} />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "История решений" }));
    const item = screen.getByRole("listitem");
    expect(item.textContent).toContain("Вернуть в разбор");
    expect(item.textContent).not.toMatch(/этап.*этап/i);
    expect(item.textContent).not.toContain("Статус «Не разобрано», этап «возвращена в разбор»");
    expect(item.textContent).not.toContain("Возвращено в разбор");
  });
});

describe("FindingCard: вкладки и PDF", () => {
  it("показывает четыре вкладки и переключает панели", () => {
    render(
      <FindingCard projectId={1} run={run} finding={finding} canDecide={false} onDecided={() => {}} />,
    );
    expect(screen.getByRole("tab", { name: "Суть несоответствия" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Краткое описание")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "История решений" }));
    expect(screen.getByRole("tab", { name: "История решений" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Решений пока нет.")).toBeInTheDocument();
  });

  it("ссылка ref открывает PDF на странице во вкладке «Документ»", () => {
    render(
      <FindingCard projectId={1} run={run} finding={finding} canDecide={false} onDecided={() => {}} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "ФТТ1, стр. 3" }));
    expect(screen.getByRole("tab", { name: "Документ" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    const iframe = screen.getByTestId("finding-pdf-iframe");
    expect(iframe).toHaveAttribute("src", expect.stringContaining("/assets/10"));
    expect(iframe.getAttribute("src")).toMatch(/#page=3$/);
  });

  it("«ПМИ сц. N» в refs относит к блоку «Сценарии», «Требования» только пункты", () => {
    const mixed: FindingDetail = {
      ...finding,
      refs: [
        { label: "ФТТ1 п. 4.1", pdf: "ФТТ1.pdf", page: 2 },
        { label: "ПМИ1 сц. 6", pdf: "ПМИ1.pdf", page: 1 },
      ],
    };
    render(
      <FindingCard projectId={1} run={run} finding={mixed} canDecide={false} onDecided={() => {}} />,
    );
    expect(screen.getByText("Требования")).toBeInTheDocument();
    const scenarioHeadings = screen.getAllByText("Сценарии");
    expect(scenarioHeadings.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("button", { name: "ФТТ1 п. 4.1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ПМИ1 сц. 6" })).toBeInTheDocument();
  });
});
