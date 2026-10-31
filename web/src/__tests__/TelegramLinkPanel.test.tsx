import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TelegramLinkPanel from "@/components/TelegramLinkPanel";

const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    telegramStatus: vi.fn(),
    telegramStart: vi.fn(),
    telegramConfirm: vi.fn(),
    telegramUnbind: vi.fn(),
  },
}));

vi.mock("@/api/client", () => ({ api: mockApi }));

const status = (state: string, extra = {}) => ({
  available: true,
  state,
  username: "",
  external_user_id: "",
  ...extra,
});

describe("TelegramLinkPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("без бота не предлагает привязку", async () => {
    mockApi.telegramStatus.mockResolvedValue({ ...status("none"), available: false });
    render(<TelegramLinkPanel />);
    expect(await screen.findByText(/Привязка недоступна/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Привязать Telegram" })).toBeNull();
  });

  it("выдаёт ссылку на бота", async () => {
    mockApi.telegramStatus
      .mockResolvedValueOnce(status("none"))
      .mockResolvedValue(status("waiting_start"));
    mockApi.telegramStart.mockResolvedValue({
      deep_link: "https://t.me/paneltestbot?start=bind_code",
      expires_in: 600,
    });
    render(<TelegramLinkPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "Привязать Telegram" }));
    const link = await screen.findByRole("link", { name: "Открыть бота" });
    expect(link).toHaveAttribute("href", "https://t.me/paneltestbot?start=bind_code");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("показывает аккаунт и подтверждает паролем", async () => {
    mockApi.telegramStatus
      .mockResolvedValueOnce(
        status("waiting_confirm", { username: "ivan", external_user_id: "7900000000" }),
      )
      .mockResolvedValue(status("active", { username: "ivan" }));
    mockApi.telegramConfirm.mockResolvedValue({ ok: true, state: "active", username: "ivan" });
    render(<TelegramLinkPanel />);
    expect(await screen.findByText(/ivan \(id 7900000000\)/)).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText("Пароль"), "secret-password");
    await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await waitFor(() =>
      expect(mockApi.telegramConfirm).toHaveBeenCalledWith("secret-password", "7900000000"),
    );
    expect(await screen.findByText("Привязан аккаунт: ivan")).toBeInTheDocument();
  });

  it("чужой аккаунт можно отменить", async () => {
    mockApi.telegramStatus
      .mockResolvedValueOnce(
        status("waiting_confirm", { username: "evil", external_user_id: "666" }),
      )
      .mockResolvedValue(status("none"));
    mockApi.telegramUnbind.mockResolvedValue({ ok: true, removed: true });
    render(<TelegramLinkPanel />);
    await userEvent.click(await screen.findByRole("button", { name: "Отменить" }));
    expect(await screen.findByRole("button", { name: "Привязать Telegram" })).toBeInTheDocument();
  });

  it("показывает ошибку неверного пароля", async () => {
    mockApi.telegramStatus.mockResolvedValue(
      status("waiting_confirm", { username: "ivan", external_user_id: "1" }),
    );
    mockApi.telegramConfirm.mockRejectedValue(new Error("invalid credentials"));
    render(<TelegramLinkPanel />);
    await userEvent.type(await screen.findByPlaceholderText("Пароль"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    expect(await screen.findByText("invalid credentials")).toBeInTheDocument();
  });
});
