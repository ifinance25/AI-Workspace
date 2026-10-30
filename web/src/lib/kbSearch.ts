import { useSyncExternalStore } from "react";

/** Переключатель «Поиск по Базе знаний»: общий для всех чатов этого браузера. */
export const KB_SEARCH_STORAGE_KEY = "kb-search-on";
const CHANGE_EVENT = "kb-search-change";

// Запасное хранилище на случай, когда localStorage недоступен (приватный режим).
let memoryValue = false;
// Последняя запись не удалась (например, квота): в localStorage старое значение.
let storageStale = false;

export function getKbSearchOn(): boolean {
  if (typeof window === "undefined" || storageStale) return memoryValue;
  try {
    return window.localStorage.getItem(KB_SEARCH_STORAGE_KEY) === "1";
  } catch {
    return memoryValue;
  }
}

export function setKbSearchOn(on: boolean): void {
  memoryValue = on;
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KB_SEARCH_STORAGE_KEY, on ? "1" : "0");
    storageStale = false;
  } catch {
    /* localStorage недоступен: держим в памяти */
    storageStale = true;
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(onStoreChange: () => void): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key === KB_SEARCH_STORAGE_KEY || e.key === null) onStoreChange();
  };
  window.addEventListener("storage", onStorage);
  window.addEventListener(CHANGE_EVENT, onStoreChange);
  return () => {
    window.removeEventListener("storage", onStorage);
    window.removeEventListener(CHANGE_EVENT, onStoreChange);
  };
}

export function useKbSearchOn(): boolean {
  return useSyncExternalStore(subscribe, getKbSearchOn, () => false);
}
