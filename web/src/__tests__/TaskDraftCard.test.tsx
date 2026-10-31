import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const officeRequest = vi.hoisted(() => vi.fn());
vi.mock("@/components/office/officeApi", () => ({ officeRequest }));

import { Markdown } from "@/lib/Markdown";

const draft = {
  project_id: 7,
  project: "Факт",
  subject: "Проверить оплату",
  description: "Счёт за октябрь",
  due_date: "2026-12-01",
  signature: "abc123",
};
const block = "Вот черновик:\n\n```pm-task\n" + JSON.stringify(draft) + "\n```\n";

describe("блок pm-task в ответе чата", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("показывает карточку и создаёт задачу только по кнопке", async () => {
    officeRequest.mockResolvedValue({ updated: true, issue: { id: 321 } });
    render(
      <MemoryRouter>
        <Markdown>{block}</Markdown>
      </MemoryRouter>,
    );
    expect(screen.getByText("Проверить оплату")).toBeInTheDocument();
    expect(officeRequest).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Создать в Redmine" }));
    await waitFor(() => expect(screen.getByText(/Задача №321 создана/)).toBeInTheDocument());
    expect(officeRequest).toHaveBeenCalledWith(
      "POST",
      "/api/office/projects/7/redmine/proposals",
      expect.objectContaining({ subject: "Проверить оплату", signature: "abc123" }),
    );
  });

  it("показывает ошибку и оставляет кнопку", async () => {
    officeRequest.mockRejectedValue(new Error("Карточка не от чата или изменена"));
    render(
      <MemoryRouter>
        <Markdown>{block}</Markdown>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Создать в Redmine" }));
    await waitFor(() =>
      expect(screen.getByText("Карточка не от чата или изменена")).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Создать в Redmine" })).toBeInTheDocument();
  });

  it("битый JSON остаётся обычным кодом, кнопки нет", () => {
    render(
      <MemoryRouter>
        <Markdown>{"```pm-task\nне json\n```"}</Markdown>
      </MemoryRouter>,
    );
    expect(screen.queryByRole("button", { name: "Создать в Redmine" })).toBeNull();
    expect(screen.getByText("не json")).toBeInTheDocument();
  });
});
