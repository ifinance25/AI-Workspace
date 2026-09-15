import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

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

import ChatPage from "@/routes/ChatPage";

describe("ChatPage: узкий экран", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.listProjects.mockResolvedValue([]);
    mockApi.listSessions.mockResolvedValue([]);
    window.matchMedia = ((query: string) => ({
      matches: query.includes("max-width: 1023px"),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    })) as unknown as typeof window.matchMedia;
  });

  it("прячет список чатов за кнопкой меню", async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("button", { name: "Открыть список чатов" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Выберите чат или создайте новый/)).toBeInTheDocument();
  });
});
