import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { TeamInfo } from "@/components/office/membersApi";

const mockApi = vi.hoisted(() => ({
  team: vi.fn(),
  add: vi.fn(),
  setRole: vi.fn(),
  remove: vi.fn(),
}));
vi.mock("@/components/office/membersApi", () => ({ membersApi: mockApi }));

import MembersScreen from "@/components/office/MembersScreen";

const roles = [
  { key: "project_manager", label: "Менеджер проекта" },
  { key: "tester", label: "Тестировщик" },
];

function team(canManage: boolean): TeamInfo {
  return {
    can_manage: canManage,
    roles,
    members: [
      { user_id: 1, username: "lead", role: "project_manager", label: "Менеджер проекта", added_at: "" },
      { user_id: 2, username: "qa", role: "tester", label: "Тестировщик", added_at: "" },
    ],
  };
}

function open() {
  return render(
    <MemoryRouter>
      <MembersScreen projectId={7} />
    </MemoryRouter>,
  );
}

describe("MembersScreen", () => {
  beforeEach(() => {
    Object.values(mockApi).forEach((fn) => fn.mockReset());
  });

  it("не менеджеру показывает только список без правок", async () => {
    mockApi.team.mockResolvedValue(team(false));
    open();
    await screen.findByText("qa");
    expect(screen.queryByRole("button", { name: "Добавить" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Убрать" })).toBeNull();
    expect(screen.queryByLabelText("Роль: qa")).toBeNull();
  });

  it("менеджер добавляет участника по логину", async () => {
    mockApi.team.mockResolvedValue(team(true));
    mockApi.add.mockResolvedValue({ user_id: 3, role: "tester" });
    open();
    await screen.findByText("qa");
    fireEvent.change(screen.getByLabelText("Логин учётки"), { target: { value: " newbie " } });
    fireEvent.click(screen.getByRole("button", { name: "Добавить" }));
    await waitFor(() => expect(mockApi.add).toHaveBeenCalledWith(7, "newbie", "tester"));
    await waitFor(() => expect(mockApi.team).toHaveBeenCalledTimes(2));
  });

  it("менеджер меняет роль и видит ошибку сервера", async () => {
    mockApi.team.mockResolvedValue(team(true));
    mockApi.setRole.mockRejectedValue(
      new Error('409 Conflict: {"detail":"В проекте должен остаться менеджер проекта"}'),
    );
    open();
    await screen.findByText("lead");
    fireEvent.change(screen.getByLabelText("Роль: lead"), { target: { value: "tester" } });
    await waitFor(() => expect(mockApi.setRole).toHaveBeenCalledWith(7, 1, "tester"));
    expect(await screen.findByRole("alert")).toHaveTextContent("должен остаться менеджер");
  });
});
