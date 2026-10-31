import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const officeRequest = vi.hoisted(() => vi.fn());
vi.mock("@/components/office/officeApi", () => ({ officeRequest }));

import VersionInfo from "@/components/VersionInfo";
import { UI_VERSION } from "@/lib/version";

describe("VersionInfo", () => {
  beforeEach(() => vi.clearAllMocks());

  it("показывает версию сервера и интерфейса без предупреждения, если они равны", async () => {
    officeRequest.mockResolvedValue({
      commit: UI_VERSION.commit,
      committed_at: "2026-10-31T10:16:34+03:00",
      started_at: "2026-10-31T07:36:10+00:00",
    });
    render(<VersionInfo />);
    expect(await screen.findByText(new RegExp(`Сервер: ${UI_VERSION.commit}`))).toBeInTheDocument();
    expect(screen.queryByText(/Версии разные/)).toBeNull();
  });

  it("предупреждает, если сервер и интерфейс разной версии", async () => {
    officeRequest.mockResolvedValue({ commit: "zzzzzzz", committed_at: "", started_at: "" });
    render(<VersionInfo />);
    expect(await screen.findByText(/Версии разные/)).toBeInTheDocument();
  });

  it("не падает, если сервер не ответил", async () => {
    officeRequest.mockRejectedValue(new Error("401"));
    render(<VersionInfo />);
    expect(await screen.findByText(/Сервер: нет данных/)).toBeInTheDocument();
  });
});
