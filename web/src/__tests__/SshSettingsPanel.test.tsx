import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SshSettingsPanel from "@/components/SshSettingsPanel";
import { api } from "@/api/client";
import type { SshProfileInfo } from "@/lib/types";

vi.mock("@/api/client", () => ({
  api: {
    getSsh: vi.fn(),
    saveSsh: vi.fn(),
    deleteSsh: vi.fn(),
  },
}));

const empty: SshProfileInfo = {
  enabled: true,
  configured: false,
  host: "",
  port: 22,
  username: "",
  has_key: false,
  fingerprint: null,
};

describe("SshSettingsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads empty form and saves host plus key", async () => {
    vi.mocked(api.getSsh).mockResolvedValue(empty);
    vi.mocked(api.saveSsh).mockResolvedValue({
      ...empty,
      configured: true,
      host: "example.com",
      username: "ubuntu",
      has_key: true,
      fingerprint: "SHA256:abcd",
    });
    render(<SshSettingsPanel />);
    const host = await screen.findByPlaceholderText("ai-panel.duckdns.org");
    await userEvent.type(host, "example.com");
    await userEvent.type(screen.getByPlaceholderText("ubuntu"), "ubuntu");
    await userEvent.type(
      screen.getByPlaceholderText("-----BEGIN OPENSSH PRIVATE KEY-----"),
      "-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----",
    );
    await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() => {
      expect(api.saveSsh).toHaveBeenCalled();
    });
    const body = vi.mocked(api.saveSsh).mock.calls[0][0];
    expect(body.host).toBe("example.com");
    expect(body.username).toBe("ubuntu");
    expect(body.private_key).toContain("BEGIN OPENSSH PRIVATE KEY");
    expect(
      await screen.findByText(/Сохранено/),
    ).toBeInTheDocument();
  });

  it("shows disabled message when encryption is off", async () => {
    vi.mocked(api.getSsh).mockResolvedValue({ ...empty, enabled: false });
    render(<SshSettingsPanel />);
    expect(
      await screen.findByText(/выключен на сервере/),
    ).toBeInTheDocument();
  });

  it("shows fingerprint when a key is already saved", async () => {
    vi.mocked(api.getSsh).mockResolvedValue({
      enabled: true,
      configured: true,
      host: "box.example",
      port: 22,
      username: "ubuntu",
      has_key: true,
      fingerprint: "SHA256:abcd",
    });
    render(<SshSettingsPanel />);
    expect(await screen.findByDisplayValue("box.example")).toBeInTheDocument();
    expect(screen.getByText(/SHA256:abcd/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Удалить ключ" })).toBeInTheDocument();
  });
});
