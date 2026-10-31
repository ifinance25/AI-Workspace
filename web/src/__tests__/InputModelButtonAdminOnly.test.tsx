import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InputModelButton from "@/components/InputModelButton";

const mocks = vi.hoisted(() => ({ user: { is_admin: false } as { is_admin: boolean } | null }));

vi.mock("@/auth/AuthContext", () => ({ useAuth: () => ({ user: mocks.user }) }));
vi.mock("@/lib/useModelInfo", () => ({
  useModelInfo: () => ({
    info: {
      current: "claude-sonnet-5-5",
      permission_mode: "default",
      known: [{ id: "claude-sonnet-5-5", label: "Claude Sonnet 5.5", hint: "" }],
    },
    error: null,
    setModel: vi.fn(),
  }),
}));

describe("InputModelButton: только администратор", () => {
  beforeEach(() => {
    mocks.user = { is_admin: false };
  });

  it("обычному пользователю кнопки нет", () => {
    render(<InputModelButton />);
    expect(screen.queryByTitle("Сменить модель Claude")).toBeNull();
  });

  it("без входа кнопки нет", () => {
    mocks.user = null;
    render(<InputModelButton />);
    expect(screen.queryByTitle("Сменить модель Claude")).toBeNull();
  });

  it("администратору кнопка видна", () => {
    mocks.user = { is_admin: true };
    render(<InputModelButton />);
    expect(screen.getByTitle("Сменить модель Claude")).toBeTruthy();
  });
});
