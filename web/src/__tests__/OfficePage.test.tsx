import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// Оболочка проектного офиса: список проектов (пока пустой) и страница проекта
// с тремя вкладками. Содержимое вкладок заполняют следующие таски.
const mockOffice = vi.hoisted(() => ({
  listProjects: vi.fn(),
  getProject: vi.fn(),
}));
vi.mock("@/components/office/officeApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/office/officeApi")>();
  return { ...actual, officeApi: mockOffice };
});

const mockApi = vi.hoisted(() => ({
  listProjects: vi.fn(),
  listSessions: vi.fn(),
}));
vi.mock("@/api/client", () => ({ api: mockApi }));

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, username: "tester", is_admin: false },
  }),
}));

vi.mock("@/components/SettingsModal", () => ({ default: () => null }));

import OfficePage from "@/routes/OfficePage";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/office" element={<OfficePage />} />
        <Route path="/office/:id" element={<OfficePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("OfficePage: оболочка проектного офиса", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.listProjects.mockResolvedValue([]);
    mockApi.listSessions.mockResolvedValue([]);
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    })) as unknown as typeof window.matchMedia;
  });

  it("пустой список: «Проектов нет» и кнопка «Новый проект»", async () => {
    mockOffice.listProjects.mockResolvedValue([]);
    renderAt("/office");
    expect(await screen.findByText("Проектов нет")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Новый проект" })).toBeInTheDocument();
  });

  it("список ведёт на страницу проекта", async () => {
    mockOffice.listProjects.mockResolvedValue([
      { id: 7, name: "Лендинг", work_kind: "", nature: "", project_type: "small", status: "active" },
    ]);
    renderAt("/office");
    expect(await screen.findByRole("link", { name: "Лендинг" })).toHaveAttribute(
      "href",
      "/office/7",
    );
    expect(screen.queryByText("Проектов нет")).not.toBeInTheDocument();
  });

  it("страница проекта показывает вкладки Паспорт, Бриф, Задание", async () => {
    mockOffice.getProject.mockResolvedValue({
      id: 7, name: "Лендинг", work_kind: "", nature: "", project_type: "small", status: "active",
    });
    renderAt("/office/7");
    expect(await screen.findByRole("heading", { name: "Лендинг" })).toBeInTheDocument();
    for (const label of ["Паспорт", "Бриф", "Задание"]) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument();
    }
    expect(mockOffice.getProject).toHaveBeenCalledWith(7);
  });

  it("нечисловой id: «Проект не найден» без запроса к API", async () => {
    renderAt("/office/abc");
    expect(await screen.findByText("Проект не найден")).toBeInTheDocument();
    expect(mockOffice.getProject).not.toHaveBeenCalled();
  });

  it("мок не теряет officeRequest, которым пользуются вкладки", async () => {
    const mod = await import("@/components/office/officeApi");
    expect(typeof mod.officeRequest).toBe("function");
  });
});
