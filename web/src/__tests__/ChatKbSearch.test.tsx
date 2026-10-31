import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import Chat from "@/components/Chat";
import { KB_SEARCH_STORAGE_KEY, setKbSearchOn } from "@/lib/kbSearch";
import type { Session } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  send: vi.fn(),
  user: { id: 1, username: "tester", is_admin: false, kb_search_enabled: true },
}));

vi.mock("@/api/ws", () => ({
  // Поле ввода заблокировано, пока сокет не открыт.
  openSessionWs: (_uuid: string, _onMessage: unknown, handlers: { onOpen: () => void }) => {
    queueMicrotask(() => handlers.onOpen());
    return { send: mocks.send, close: vi.fn() };
  },
}));
vi.mock("@/api/client", () => ({
  // Chat при монтировании зовёт много методов; для отправки важен только сокет.
  api: new Proxy(
    {},
    { get: (_target, name) => (name === "then" ? undefined : vi.fn().mockResolvedValue([])) },
  ),
}));
vi.mock("@/auth/AuthContext", () => ({ useAuth: () => ({ user: mocks.user }) }));
vi.mock("@/lib/useModelInfo", () => ({ useModelInfo: () => ({}) }));
vi.mock("@/components/InputModelButton", () => ({ default: () => null }));
vi.mock("@/components/DocsPanel", () => ({ default: () => null }));
vi.mock("@/components/files/FilesPanel", () => ({ default: () => null }));
vi.mock("@/components/artifacts/ArtifactsPanel", () => ({ default: () => null }));
vi.mock("@/components/ProjectMembersPanel", () => ({ default: () => null }));

const session = {
  session_uuid: "s1",
  project_name: "demo",
  project_path: "/tmp/demo",
  notes: "заголовок",
} as unknown as Session;

const NAME = "Поиск по базе знаний и задачам Redmine";
const loupe = () => screen.getByRole("button", { name: NAME });
const send = async (text: string) => {
  await waitFor(() => expect(screen.getByRole("textbox")).toBeEnabled());
  fireEvent.change(screen.getByRole("textbox"), { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: /Отправить|Send/i }));
};
const lastMessage = () =>
  mocks.send.mock.calls.map(([message]) => message).filter((m) => m.type === "user_message").at(-1);

beforeEach(() => {
  mocks.send.mockClear();
  mocks.user.kb_search_enabled = true;
  window.localStorage.clear();
  setKbSearchOn(false);
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
});

describe("Chat: поиск по Базе знаний", () => {
  it("лупа включена: сообщение уходит с kb_search: true", async () => {
    render(<Chat session={session} />);
    fireEvent.click(await waitFor(loupe));
    await send("вопрос");
    await waitFor(() => expect(lastMessage()).toBeTruthy());
    expect(lastMessage()).toMatchObject({ type: "user_message", text: "вопрос", kb_search: true });
  });

  it("лупа выключена: поля kb_search в сообщении нет", async () => {
    render(<Chat session={session} />);
    await waitFor(loupe);
    await send("вопрос");
    await waitFor(() => expect(lastMessage()).toBeTruthy());
    expect(lastMessage()).not.toHaveProperty("kb_search");
  });

  it("флаг из профиля доходит до поля ввода: нет сервера, кнопка выключена", async () => {
    mocks.user.kb_search_enabled = false;
    window.localStorage.setItem(KB_SEARCH_STORAGE_KEY, "1");
    render(<Chat session={session} />);
    const button = await waitFor(loupe);
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "Поиск по базе и задачам не подключён");
    await send("вопрос");
    await waitFor(() => expect(lastMessage()).toBeTruthy());
    expect(lastMessage()).not.toHaveProperty("kb_search");
  });
});
