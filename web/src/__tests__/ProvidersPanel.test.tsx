import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import ProvidersPanel from "@/components/ProvidersPanel";
import { api, ApiError } from "@/api/client";
import type { ProvidersInfo } from "@/lib/types";

const VALID_KEY = "sk-ant-" + "a".repeat(48);

function emptyInfo(overrides: Partial<ProvidersInfo> = {}): ProvidersInfo {
  return {
    enabled: true,
    privileged: false,
    active_provider: "claude",
    providers: [
      {
        id: "claude",
        label: "Claude Code",
        description: "Подписка Claude",
        key_placeholder: "sk-ant-…",
        key_hint: "Ключ Anthropic",
        how_to_url: "https://console.anthropic.com/settings/keys",
        oauth_url: "https://claude.ai/login",
        oauth_label: "Подключить подписку",
        base_url: null,
        base_url_editable: false,
        default_model: "claude-sonnet-4-6",
        models: [
          { id: "claude-haiku-4-5-20251001", label: "Haiku", hint: "быстрый" },
          { id: "claude-sonnet-4-6", label: "Sonnet", hint: "баланс" },
          { id: "claude-opus-4-8", label: "Opus", hint: "сильный" },
        ],
        connected: false,
        status: null,
        last4: null,
        auth_kind: null,
        current_model: "claude-sonnet-4-6",
        active: true,
      },
      {
        id: "openai",
        label: "OpenAI",
        description: "Ключ OpenAI",
        key_placeholder: "sk-…",
        key_hint: "Ключ OpenAI",
        how_to_url: "https://platform.openai.com/api-keys",
        oauth_url: null,
        oauth_label: null,
        base_url: null,
        base_url_editable: true,
        default_model: "gpt-4.1",
        models: [{ id: "gpt-4.1", label: "GPT-4.1", hint: "основная" }],
        connected: false,
        status: null,
        last4: null,
        auth_kind: null,
        current_model: "gpt-4.1",
        active: false,
      },
      {
        id: "cursor",
        label: "Cursor API",
        description: "Ключ Cursor",
        key_placeholder: "key_…",
        key_hint: "Ключ Cursor",
        how_to_url: "https://cursor.com/dashboard?tab=integrations",
        oauth_url: null,
        oauth_label: null,
        base_url: null,
        base_url_editable: true,
        default_model: "composer-2",
        models: [{ id: "composer-2", label: "Composer", hint: "код" }],
        connected: false,
        status: null,
        last4: null,
        auth_kind: null,
        current_model: "composer-2",
        active: false,
      },
      {
        id: "kimi",
        label: "Kimi Code",
        description: "Moonshot Kimi",
        key_placeholder: "sk-kimi-…",
        key_hint: "Ключ Moonshot",
        how_to_url: "https://platform.moonshot.ai/console/api-keys",
        oauth_url: null,
        oauth_label: null,
        base_url: "https://api.moonshot.ai/anthropic",
        base_url_editable: false,
        default_model: "kimi-k2.5",
        models: [{ id: "kimi-k2.5", label: "Kimi K2.5", hint: "код" }],
        connected: false,
        status: null,
        last4: null,
        auth_kind: null,
        current_model: "kimi-k2.5",
        active: false,
      },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(api, "listProviders").mockResolvedValue(emptyInfo());
});

describe("ProvidersPanel", () => {
  it("shows Claude, OpenAI, Cursor, Kimi groups and Haiku/Sonnet/Opus", async () => {
    render(<ProvidersPanel privileged={false} />);
    expect(await screen.findByText("Claude Code")).toBeInTheDocument();
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Cursor API")).toBeInTheDocument();
    expect(screen.getByText("Kimi Code")).toBeInTheDocument();
    expect(screen.getByText("Haiku")).toBeInTheDocument();
    expect(screen.getByText("Sonnet")).toBeInTheDocument();
    expect(screen.getByText("Opus")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Подключить подписку" })).toHaveAttribute(
      "href",
      "https://claude.ai/login",
    );
  });

  it("shows unprivileged helper text", async () => {
    render(<ProvidersPanel privileged={false} />);
    expect(
      await screen.findByText(/Без ключа отправка сообщений недоступна/i),
    ).toBeInTheDocument();
  });

  it("shows privileged helper text", async () => {
    vi.spyOn(api, "listProviders").mockResolvedValue(emptyInfo({ privileged: true }));
    render(<ProvidersPanel privileged={true} />);
    expect(
      await screen.findByText(/по умолчанию подписка сервиса/i),
    ).toBeInTheDocument();
  });

  it("rejects a malformed Claude key client-side", async () => {
    const put = vi.spyOn(api, "putProvider");
    render(<ProvidersPanel privileged={false} />);
    await screen.findByText("Claude Code");
    fireEvent.change(screen.getByPlaceholderText("sk-ant-…"), {
      target: { value: "not-a-key" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Сохранить" })[0]);
    expect(
      await screen.findByText(/должен начинаться с sk-ant-/i),
    ).toBeInTheDocument();
    expect(put).not.toHaveBeenCalled();
  });

  it("saves a valid Claude key", async () => {
    const put = vi
      .spyOn(api, "putProvider")
      .mockResolvedValue({ status: "active", message: "API key saved" });
    render(<ProvidersPanel privileged={false} />);
    await screen.findByText("Claude Code");
    fireEvent.change(screen.getByPlaceholderText("sk-ant-…"), {
      target: { value: VALID_KEY },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Сохранить" })[0]);
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("claude", { api_key: VALID_KEY }),
    );
    expect(await screen.findByText("API key saved")).toBeInTheDocument();
  });

  it("shows a disabled notice when the feature is dormant (501)", async () => {
    vi.spyOn(api, "listProviders").mockRejectedValue(
      new ApiError(501, "501 Not Implemented: api key store not configured"),
    );
    render(<ProvidersPanel privileged={false} />);
    expect(await screen.findByText(/выключено на сервере/i)).toBeInTheDocument();
  });

  it("shows API key fields and Save in Claude and OpenAI groups", async () => {
    render(<ProvidersPanel privileged={false} />);
    await screen.findByText("Claude Code");

    const claude = screen.getByText("Claude Code").closest("section");
    expect(claude).not.toBeNull();
    expect(within(claude!).getByLabelText(/API-ключ Anthropic/i)).toBeInTheDocument();
    expect(within(claude!).getByPlaceholderText("sk-ant-…")).toBeInTheDocument();
    expect(within(claude!).getByRole("button", { name: "Сохранить" })).toBeInTheDocument();
    expect(
      within(claude!).getByRole("link", { name: "Подключить подписку" }),
    ).toBeInTheDocument();

    const openai = screen.getByText("OpenAI").closest("section");
    expect(openai).not.toBeNull();
    expect(within(openai!).getByLabelText(/API-ключ OpenAI/i)).toBeInTheDocument();
    expect(within(openai!).getByPlaceholderText("sk-…")).toBeInTheDocument();
    expect(within(openai!).getByRole("button", { name: "Сохранить" })).toBeInTheDocument();
  });

  it("saves a valid OpenAI key via /api/providers/openai", async () => {
    const openaiKey = "sk-" + "o".repeat(24);
    const put = vi
      .spyOn(api, "putProvider")
      .mockResolvedValue({ status: "active", message: "API key saved" });
    render(<ProvidersPanel privileged={false} />);
    await screen.findByText("OpenAI");
    const openai = screen.getByText("OpenAI").closest("section")!;
    fireEvent.change(within(openai).getByPlaceholderText("sk-…"), {
      target: { value: openaiKey },
    });
    fireEvent.click(within(openai).getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("openai", { api_key: openaiKey }),
    );
    expect(await screen.findByText("API key saved")).toBeInTheDocument();
  });
});
