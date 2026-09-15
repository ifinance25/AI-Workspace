// M1: протухшая сессия (401 посреди работы) → глобальный сигнал разлогина.
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

function fakeResp(status: number, body = "") {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    text: async () => body,
    json: async () => ({}),
  };
}

describe("api 401 → auth:unauthorized", () => {
  beforeEach(() => {
    vi.resetModules();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("диспатчит событие на 401 для обычного запроса", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => fakeResp(401, "nope")));
    const { api, AUTH_UNAUTHORIZED_EVENT } = await import("@/api/client");
    const handler = vi.fn();
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
    await expect(api.listSessions()).rejects.toBeTruthy();
    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
  });

  it("НЕ диспатчит на 401 для /api/auth/* (неверные креды на логине)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => fakeResp(401, "bad creds")));
    const { api, AUTH_UNAUTHORIZED_EVENT } = await import("@/api/client");
    const handler = vi.fn();
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
    await expect(api.login("u", "wrong")).rejects.toBeTruthy();
    expect(handler).not.toHaveBeenCalled();
    window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
  });

  it("диспатчит событие на 401 при загрузке файла (uploadFile)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => fakeResp(401, "nope")));
    const { api, AUTH_UNAUTHORIZED_EVENT } = await import("@/api/client");
    const handler = vi.fn();
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
    const file = new File(["x"], "a.txt", { type: "text/plain" });
    await expect(api.uploadFile("uuid", file)).rejects.toBeTruthy();
    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
  });

  it("диспатчит событие на 401 при загрузке в файлы проекта", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => fakeResp(401, "nope")));
    const { api, AUTH_UNAUTHORIZED_EVENT } = await import("@/api/client");
    const handler = vi.fn();
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
    const file = new File(["x"], "a.txt", { type: "text/plain" });
    await expect(api.uploadProjectFiles("/p", "", [file])).rejects.toBeTruthy();
    expect(handler).toHaveBeenCalledTimes(1);
    window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
  });

  it("не диспатчит на успешном ответе", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => fakeResp(200, "[]")));
    const { api, AUTH_UNAUTHORIZED_EVENT } = await import("@/api/client");
    const handler = vi.fn();
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
    await api.listSessions();
    expect(handler).not.toHaveBeenCalled();
    window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handler);
  });
});

describe("uploadProjectFiles", () => {
  beforeEach(() => {
    vi.resetModules();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("шлёт несколько файлов полем files в текущую папку", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "OK",
      text: async () => "",
      json: async () => ({ uploaded: [], errors: [] }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const { api } = await import("@/api/client");
    const a = new File(["a"], "a.txt", { type: "text/plain" });
    const b = new File(["b"], "b.txt", { type: "text/plain" });
    await api.uploadProjectFiles("/proj", "docs", [a, b]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, { body: FormData }];
    expect(url).toContain("/api/files/upload");
    expect(url).toContain("dir=docs");
    expect(init.body.getAll("files")).toHaveLength(2);
  });
});
