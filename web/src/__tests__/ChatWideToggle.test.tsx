import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

// Лёгкая проверка без полной сборки чата: кнопка и переменные ширины на месте.
describe("Chat: широкий режим", () => {
  const src = readFileSync("src/components/Chat.tsx", "utf8");
  it("есть кнопка переключения и 80% в широком режиме", () => {
    expect(src).toContain('aria-label="Широкий чат"');
    expect(src).toContain('wide ? "80%"');
  });
  it("лента и ввод читают переменную ширины", () => {
    expect(src).toContain("max-w-[var(--chat-w)]");
    expect(readFileSync("src/components/MessageInput.tsx", "utf8")).toContain("var(--chat-w,48rem)");
  });
});
