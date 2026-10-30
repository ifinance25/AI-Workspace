import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getKbSearchOn, KB_SEARCH_STORAGE_KEY, setKbSearchOn } from "@/lib/kbSearch";

const quotaExceeded = () => {
  throw new DOMException("quota", "QuotaExceededError");
};

describe("kbSearch: хранение переключателя", () => {
  beforeEach(() => {
    window.localStorage.clear();
    setKbSearchOn(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    setKbSearchOn(false);
  });

  it("обычная запись идёт в localStorage", () => {
    setKbSearchOn(true);
    expect(window.localStorage.getItem(KB_SEARCH_STORAGE_KEY)).toBe("1");
    expect(getKbSearchOn()).toBe(true);
  });

  it("упала только запись: чтение видит новое значение, а не старое из localStorage", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(quotaExceeded);
    setKbSearchOn(true);
    expect(window.localStorage.getItem(KB_SEARCH_STORAGE_KEY)).toBe("0");
    expect(getKbSearchOn()).toBe(true);
    setKbSearchOn(false);
    expect(getKbSearchOn()).toBe(false);
  });

  it("после удачной записи снова читается localStorage", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(quotaExceeded);
    setKbSearchOn(true);
    spy.mockRestore();
    setKbSearchOn(true);
    window.localStorage.setItem(KB_SEARCH_STORAGE_KEY, "0");
    expect(getKbSearchOn()).toBe(false);
  });

  it("упало и чтение: остаётся значение из памяти", () => {
    setKbSearchOn(true);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(quotaExceeded);
    expect(getKbSearchOn()).toBe(true);
  });
});
