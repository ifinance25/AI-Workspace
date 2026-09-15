import { describe, it, expect } from "vitest";
import {
  shouldInsertNewlineOnKey,
  shouldSendOnKey,
  sendButtonTitle,
  sendKeyHint,
} from "@/lib/sendKey";

function key(
  partial: Partial<{
    key: string;
    ctrlKey: boolean;
    metaKey: boolean;
    shiftKey: boolean;
    altKey: boolean;
    isComposing: boolean;
  }>,
) {
  return {
    key: "Enter",
    ctrlKey: false,
    metaKey: false,
    shiftKey: false,
    altKey: false,
    isComposing: false,
    ...partial,
  };
}

describe("shouldSendOnKey", () => {
  it("режим enter: обычный Enter отправляет", () => {
    expect(shouldSendOnKey(key({}), "enter")).toBe(true);
  });

  it("режим enter: Shift/Ctrl/Cmd не отправляют", () => {
    expect(shouldSendOnKey(key({ shiftKey: true }), "enter")).toBe(false);
    expect(shouldSendOnKey(key({ ctrlKey: true }), "enter")).toBe(false);
    expect(shouldSendOnKey(key({ metaKey: true }), "enter")).toBe(false);
  });

  it("режим ctrlEnter: Ctrl или Cmd+Enter отправляют, обычный Enter нет", () => {
    expect(shouldSendOnKey(key({}), "ctrlEnter")).toBe(false);
    expect(shouldSendOnKey(key({ ctrlKey: true }), "ctrlEnter")).toBe(true);
    expect(shouldSendOnKey(key({ metaKey: true }), "ctrlEnter")).toBe(true);
    expect(shouldSendOnKey(key({ shiftKey: true }), "ctrlEnter")).toBe(false);
  });

  it("IME composition не отправляет", () => {
    expect(shouldSendOnKey(key({ isComposing: true }), "enter")).toBe(false);
  });
});

describe("shouldInsertNewlineOnKey", () => {
  it("режим enter: Ctrl+Enter вставляет перевод строки", () => {
    expect(shouldInsertNewlineOnKey(key({ ctrlKey: true }), "enter")).toBe(true);
    expect(shouldInsertNewlineOnKey(key({}), "enter")).toBe(false);
  });

  it("режим ctrlEnter: перевод строки даёт обычный Enter, без ручной вставки", () => {
    expect(shouldInsertNewlineOnKey(key({}), "ctrlEnter")).toBe(false);
    expect(shouldInsertNewlineOnKey(key({ ctrlKey: true }), "ctrlEnter")).toBe(
      false,
    );
  });
});

describe("подсказки", () => {
  it("меняются вместе с режимом", () => {
    expect(sendKeyHint("enter")).toContain("Enter — отправить");
    expect(sendKeyHint("ctrlEnter")).toContain("Ctrl+Enter — отправить");
    expect(sendButtonTitle("enter")).toContain("Enter");
    expect(sendButtonTitle("ctrlEnter")).toContain("Ctrl+Enter");
  });
});
