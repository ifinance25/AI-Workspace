import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { createRef } from "react";
import ChatOutline, { buildOutline } from "@/components/ChatOutline";

describe("buildOutline", () => {
  it("берёт только сообщения пользователя, первую непустую строку", () => {
    const items = buildOutline([
      { id: "u-1", kind: "user_message", content: "\n  Первая тема\nвторая строка" },
      { id: "t-1", kind: "text", content: "ответ" },
      { id: "u-2", kind: "user_message", content: "   " },
      { id: "u-3", kind: "user_message", content: "Вторая тема" },
    ]);
    expect(items).toEqual([
      { id: "u-1", title: "Первая тема" },
      { id: "u-3", title: "Вторая тема" },
    ]);
  });

  it("обрезает длинный заголовок", () => {
    const [it1] = buildOutline([
      { id: "u-1", kind: "user_message", content: "а".repeat(200) },
    ]);
    expect(it1.title.length).toBe(70);
    expect(it1.title.endsWith("…")).toBe(true);
  });
});

describe("ChatOutline", () => {
  it("показывает заголовок при наведении", () => {
    const ref = createRef<HTMLDivElement>();
    render(
      <ChatOutline
        scrollRef={ref}
        items={[
          { id: "a", title: "Тема А" },
          { id: "b", title: "Тема Б" },
        ]}
      />,
    );
    const btn = screen.getAllByRole("button")[1];
    expect(screen.queryByText("Тема Б", { selector: "span" })).toBeNull();
    fireEvent.mouseEnter(btn);
    expect(screen.getByText("Тема Б", { selector: "span" })).toBeInTheDocument();
  });

  it("не рисуется, если тема одна", () => {
    const ref = createRef<HTMLDivElement>();
    const { container } = render(
      <ChatOutline scrollRef={ref} items={[{ id: "a", title: "Тема А" }]} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
