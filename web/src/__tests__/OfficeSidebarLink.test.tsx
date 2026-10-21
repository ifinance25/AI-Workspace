import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

// Вошедший пользователь видит в боковой панели ссылку на проектный офис.
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

describe("Sidebar: ссылка «Проектный офис»", () => {
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

  it("ведёт на /office и видна обычному пользователю", async () => {
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("link", { name: "Проектный офис" }),
    ).toHaveAttribute("href", "/office");
  });
});
