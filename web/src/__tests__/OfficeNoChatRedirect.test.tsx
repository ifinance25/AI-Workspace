import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const mockApi = vi.hoisted(() => ({
  listProjects: vi.fn(),
  listSessions: vi.fn(),
}));
vi.mock("@/api/client", () => ({ api: mockApi }));
vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1, username: "tester", is_admin: false } }),
}));
vi.mock("@/components/SettingsModal", () => ({ default: () => null }));

import AppShell from "@/components/AppShell";

const session = {
  session_uuid: "s1",
  title: "Старый чат",
  last_activity: "2026-11-01T00:32:00Z",
};

describe("Страницы офиса не уводят в чат", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.listProjects.mockResolvedValue([]);
    mockApi.listSessions.mockResolvedValue([session]);
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    })) as unknown as typeof window.matchMedia;
  });

  it("с openLastChat=false последний чат не открывается сам", async () => {
    const onSelect = vi.fn();
    render(
      <MemoryRouter>
        <AppShell activeSessionUuid={null} openLastChat={false} onSelectSession={onSelect}>
          <p>Экран прогонов</p>
        </AppShell>
      </MemoryRouter>,
    );
    await waitFor(() => expect(mockApi.listSessions).toHaveBeenCalled());
    await screen.findByText("Экран прогонов");
    await new Promise((r) => setTimeout(r, 50));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("по умолчанию последний чат открывается, как раньше", async () => {
    const onSelect = vi.fn();
    render(
      <MemoryRouter>
        <AppShell activeSessionUuid={null} onSelectSession={onSelect}>
          <p>Чат</p>
        </AppShell>
      </MemoryRouter>,
    );
    await waitFor(() => expect(onSelect).toHaveBeenCalledTimes(1));
  });
});
