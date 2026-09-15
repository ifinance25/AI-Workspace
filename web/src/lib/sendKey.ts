import { useSyncExternalStore } from "react";

/** Какая клавиша отправляет сообщение в поле чата. */
export type SendKey = "enter" | "ctrlEnter";

const STORAGE_KEY = "ai-panel-send-key";
const CHANGE_EVENT = "ai-panel-send-key-change";

export const SEND_KEY_OPTIONS: {
  value: SendKey;
  label: string;
  hint: string;
}[] = [
  {
    value: "enter",
    label: "Enter",
    hint: "Enter отправляет сообщение, Ctrl+Enter переносит строку",
  },
  {
    value: "ctrlEnter",
    label: "Ctrl+Enter",
    hint: "Ctrl+Enter отправляет сообщение, Enter переносит строку",
  },
];

function parseSendKey(raw: string | null): SendKey {
  return raw === "ctrlEnter" ? "ctrlEnter" : "enter";
}

export function getStoredSendKey(): SendKey {
  if (typeof window === "undefined") return "enter";
  try {
    return parseSendKey(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return "enter";
  }
}

export function setStoredSendKey(key: SendKey): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, key);
  } catch {
    /* private mode */
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(onStoreChange: () => void): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY || e.key === null) onStoreChange();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(CHANGE_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(CHANGE_EVENT, onStoreChange);
  };
}

export function useSendKey(): SendKey {
  return useSyncExternalStore(subscribe, getStoredSendKey, () => "enter");
}

export type EnterKeyLike = {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
  altKey?: boolean;
  isComposing?: boolean;
  nativeEvent?: { isComposing?: boolean };
};

function composing(e: EnterKeyLike): boolean {
  return Boolean(e.isComposing || e.nativeEvent?.isComposing);
}

function hasCtrlOrMeta(e: EnterKeyLike): boolean {
  return e.ctrlKey || e.metaKey;
}

/** Enter без модификаторов: обычный перевод строки или отправка. */
export function isPlainEnter(e: EnterKeyLike): boolean {
  return (
    e.key === "Enter" &&
    !composing(e) &&
    !e.shiftKey &&
    !e.altKey &&
    !hasCtrlOrMeta(e)
  );
}

export function isModEnter(e: EnterKeyLike): boolean {
  return e.key === "Enter" && !composing(e) && hasCtrlOrMeta(e) && !e.altKey;
}

export function shouldSendOnKey(e: EnterKeyLike, mode: SendKey): boolean {
  if (mode === "enter") return isPlainEnter(e);
  return isModEnter(e);
}

/** Ctrl/Cmd+Enter в режиме «Enter отправляет»: вручную вставить перевод строки. */
export function shouldInsertNewlineOnKey(
  e: EnterKeyLike,
  mode: SendKey,
): boolean {
  return mode === "enter" && isModEnter(e);
}

export function sendKeyHint(mode: SendKey): string {
  if (mode === "ctrlEnter") {
    return "Ctrl+Enter — отправить · Enter — перенос строки · «/» — команды";
  }
  return "Enter — отправить · Ctrl+Enter — перенос строки · «/» — команды";
}

export function sendButtonTitle(mode: SendKey): string {
  return mode === "ctrlEnter" ? "Отправить (Ctrl+Enter)" : "Отправить (Enter)";
}
