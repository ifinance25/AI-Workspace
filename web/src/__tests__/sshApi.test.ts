import { describe, it, expect, vi, afterEach } from "vitest";
import { api } from "@/api/client";

afterEach(() => vi.restoreAllMocks());

function mockFetch(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: status < 400, status, statusText: "",
    text: async () => JSON.stringify(body), json: async () => body,
  })) as unknown as typeof fetch);
}

describe("ssh api", () => {
  it("getSsh GETs /api/ssh", async () => {
    mockFetch(200, { enabled: true, configured: false });
    await api.getSsh();
    expect((fetch as any).mock.calls[0][0]).toContain("/api/ssh");
  });

  it("saveSsh PUTs host and key", async () => {
    mockFetch(200, { enabled: true, configured: true, has_key: true });
    await api.saveSsh({
      host: "example.com",
      port: 22,
      username: "ubuntu",
      private_key: "KEY",
    });
    const [, opts] = (fetch as any).mock.calls[0];
    expect(opts.method).toBe("PUT");
    expect(opts.body).toContain("example.com");
    expect(opts.body).toContain("KEY");
  });

  it("deleteSsh DELETEs /api/ssh", async () => {
    mockFetch(200, { ok: true });
    await api.deleteSsh();
    const [url, opts] = (fetch as any).mock.calls[0];
    expect(opts.method).toBe("DELETE");
    expect(url).toContain("/api/ssh");
  });
});
