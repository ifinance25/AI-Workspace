import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Вкладка «Бриф»: пусто просит положить бриф, текст становится версией,
// файл не того типа отклонён и введённый текст не теряется.
const mockBrief = vi.hoisted(() => ({
  listVersions: vi.fn(),
  getVersion: vi.fn(),
  saveText: vi.fn(),
  uploadFile: vi.fn(),
}));
vi.mock("@/components/office/brief/briefApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/office/brief/briefApi")>();
  return { ...actual, briefApi: mockBrief };
});

import BriefTab from "@/components/office/brief/BriefTab";

const project = {
  id: 7, name: "Лендинг", work_kind: "", nature: "", project_type: "small", status: "active",
};
const v1 = { id: 11, number: 1, status: "draft", source: "текст", created_at: "2026-10-22T10:00:00+00:00" };

describe("BriefTab: бриф проекта", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("пусто: просьба положить бриф, пустой текст не уходит на сервер", async () => {
    mockBrief.listVersions.mockResolvedValue([]);
    render(<BriefTab project={project} />);
    expect(await screen.findByText(/Брифа ещё нет/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить версию" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Положите бриф");
    expect(mockBrief.saveText).not.toHaveBeenCalled();
  });

  it("текст сохраняется версией, версия видна в списке и открывается как Markdown", async () => {
    mockBrief.listVersions.mockResolvedValueOnce([]).mockResolvedValue([v1]);
    mockBrief.saveText.mockResolvedValue({ version: v1, created: true });
    mockBrief.getVersion.mockResolvedValue({ ...v1, markdown: "# Сайт\n\nНужен лендинг.", paragraphs: [] });
    render(<BriefTab project={project} />);
    await screen.findByText(/Брифа ещё нет/);
    fireEvent.change(screen.getByLabelText("Текст брифа"), {
      target: { value: "# Сайт\n\nНужен лендинг." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить версию" }));
    expect(await screen.findByRole("heading", { name: "Сайт" })).toBeInTheDocument();
    expect(mockBrief.saveText).toHaveBeenCalledWith(7, "# Сайт\n\nНужен лендинг.");
    expect(mockBrief.getVersion).toHaveBeenCalledWith(7, 1);
    expect(screen.getByRole("button", { name: /Версия 1.*текст/ })).toBeInTheDocument();
  });

  it("файл не того типа отклонён, введённый текст остаётся", async () => {
    mockBrief.listVersions.mockResolvedValue([]);
    mockBrief.uploadFile.mockRejectedValue(
      new Error("Файл «brief.pdf» не принят: загрузите бриф в формате .md, .txt или .docx."),
    );
    render(<BriefTab project={project} />);
    await screen.findByText(/Брифа ещё нет/);
    fireEvent.change(screen.getByLabelText("Текст брифа"), { target: { value: "Черновик" } });
    const file = new File(["%PDF"], "brief.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Загрузить файл"), { target: { files: [file] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("не принят");
    await waitFor(() => expect(mockBrief.uploadFile).toHaveBeenCalledWith(7, file));
    expect(screen.getByLabelText("Текст брифа")).toHaveValue("Черновик");
  });
});
