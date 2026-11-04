import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const mockApi = vi.hoisted(() => ({
  listProjects: vi.fn(),
  listSessions: vi.fn(),
}));
vi.mock("@/api/client", () => ({ api: mockApi }));

const mockOffice = vi.hoisted(() => ({
  getProject: vi.fn(),
  listProjects: vi.fn(),
}));
vi.mock("@/components/office/officeApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/office/officeApi")>();
  return { ...actual, officeApi: mockOffice };
});

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, username: "tester", is_admin: false },
  }),
}));

vi.mock("@/components/SettingsModal", () => ({ default: () => null }));

import ChatPage from "@/routes/ChatPage";
import OfficePage from "@/routes/OfficePage";

describe("Sidebar: проектный офис", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.listProjects.mockResolvedValue([]);
    mockApi.listSessions.mockResolvedValue([]);
    mockOffice.listProjects.mockResolvedValue([]);
    mockOffice.getProject.mockResolvedValue({
      id: 7,
      name: "Лендинг",
      work_kind: "",
      nature: "",
      project_type: "small",
      status: "active",
    });
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    })) as unknown as typeof window.matchMedia;
  });

  it("ссылка «Проектный офис» ведёт на /office", async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("link", { name: "Проектный офис" }),
    ).toHaveAttribute("href", "/office");
  });

  it("«Задачи» и «Прогоны» в основном меню на странице проекта", async () => {
    render(
      <MemoryRouter initialEntries={["/office/7"]}>
        <Routes>
          <Route path="/office/:id" element={<OfficePage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("link", { name: "Задачи" })).toHaveAttribute(
      "href",
      "/office/7/redmine",
    );
    expect(screen.getByRole("link", { name: "Прогоны" })).toHaveAttribute(
      "href",
      "/office/7/runs",
    );
    expect(screen.getByText("Основное меню")).toBeTruthy();
  });

  it("«Задачи» видны на списке офиса с первым проектом", async () => {
    mockOffice.listProjects.mockResolvedValue([
      {
        id: 7,
        name: "Лендинг",
        work_kind: "",
        nature: "",
        project_type: "small",
        status: "active",
      },
    ]);
    render(
      <MemoryRouter initialEntries={["/office"]}>
        <Routes>
          <Route path="/office" element={<OfficePage />} />
        </Routes>
      </MemoryRouter>,
    );
    await screen.findByRole("link", { name: "Лендинг" });
    expect(screen.getByRole("link", { name: "Задачи" })).toHaveAttribute(
      "href",
      "/office/7/redmine",
    );
  });
});
