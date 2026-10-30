import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import MessageInput from "@/components/MessageInput";
import { api } from "@/api/client";
import { KB_SEARCH_STORAGE_KEY } from "@/lib/kbSearch";

// Выбор модели тянет ModelInfoProvider; к поиску по базе знаний он не относится.
vi.mock("@/components/InputModelButton", () => ({ default: () => null }));

beforeEach(() => {
  window.localStorage.clear();
  vi.spyOn(api, "getSlashCommands").mockResolvedValue([]);
});

const NAME = "Поиск по Базе знаний";

const mount = (kbSearchEnabled: boolean, onSubmit = vi.fn()) => {
  const view = render(
    <MessageInput sessionUuid="s1" onSubmit={onSubmit} kbSearchEnabled={kbSearchEnabled} />,
  );
  return { onSubmit, view };
};
const btn = () => screen.getByRole("button", { name: NAME });
const field = () => screen.getByRole("textbox") as HTMLTextAreaElement;
const send = (text: string) => {
  fireEvent.change(field(), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /Отправить|Send/i }));
};

describe("MessageInput: переключатель поиска по Базе знаний", () => {
  it("кнопка стоит сразу после «Скиллы», по умолчанию выключена", () => {
    mount(true);
    expect(screen.getByTitle("Скиллы").nextElementSibling).toBe(btn());
    expect(btn()).toHaveAttribute("aria-pressed", "false");
    expect(btn()).toHaveAttribute("title", "Поиск по Базе знаний: выключен");
  });

  it("нажатие меняет aria-pressed и title, текст поля не трогает", () => {
    const { onSubmit } = mount(true);
    fireEvent.change(field(), { target: { value: "черновик" } });
    fireEvent.click(btn());
    expect(btn()).toHaveAttribute("aria-pressed", "true");
    expect(btn()).toHaveAttribute("title", "Поиск по Базе знаний: включён");
    expect(field().value).toBe("черновик");
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.click(btn());
    expect(btn()).toHaveAttribute("aria-pressed", "false");
  });

  it("состояние сохраняется в localStorage и после перемонтирования", () => {
    const { view } = mount(true);
    fireEvent.click(btn());
    expect(window.localStorage.getItem(KB_SEARCH_STORAGE_KEY)).toBe("1");
    view.unmount();
    mount(true);
    expect(btn()).toHaveAttribute("aria-pressed", "true");
  });

  it("при отправке kbSearch=true только когда включено", () => {
    const { onSubmit } = mount(true);
    send("вопрос 1");
    expect(onSubmit).toHaveBeenLastCalledWith("вопрос 1", [], false);
    fireEvent.click(btn());
    send("вопрос 2");
    expect(onSubmit).toHaveBeenLastCalledWith("вопрос 2", [], true);
  });

  it("сервер не подключён: кнопка disabled, подсказка, в отправке false даже при сохранённом Вкл", () => {
    window.localStorage.setItem(KB_SEARCH_STORAGE_KEY, "1");
    const { onSubmit } = mount(false);
    expect(btn()).toBeDisabled();
    expect(btn()).toHaveAttribute("title", "База знаний не подключена");
    expect(btn()).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(btn());
    expect(window.localStorage.getItem(KB_SEARCH_STORAGE_KEY)).toBe("1");
    send("вопрос");
    expect(onSubmit).toHaveBeenLastCalledWith("вопрос", [], false);
  });
});
