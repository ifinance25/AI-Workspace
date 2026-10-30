import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/api/client";
import type { RedmineIssue, RedmineView } from "@/components/redmine/redmineApi";

const mockRedmine = vi.hoisted(() => ({
  fetchMirror: vi.fn(),
  loadProject: vi.fn(),
  createIssue: vi.fn(),
  updateIssue: vi.fn(),
}));
vi.mock("@/components/redmine/redmineApi", () => ({ redmineApi: mockRedmine }));

const mockApi = vi.hoisted(() => ({
  listProjects: vi.fn(),
  listSessions: vi.fn(),
}));
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    api: mockApi,
  };
});

vi.mock("@/auth/AuthContext", () => ({
  useAuth: () => ({
    user: { id: 1, username: "tester", is_admin: false },
  }),
}));

vi.mock("@/components/SettingsModal", () => ({ default: () => null }));

import RedminePage from "@/routes/RedminePage";
import RedmineScreens from "@/components/redmine/RedmineScreens";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/office/:id/redmine" element={<RedminePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function issue(over: Partial<RedmineIssue> = {}): RedmineIssue {
  return {
    id: 15,
    subject: "Статья",
    description: "текст из Redmine",
    status: { id: "5", name: "Закрыта" },
    author: { user_id: 3, login: "ivan", name: "Иван" },
    assignee: { user_id: 4, login: "anna", name: "Анна" },
    start_date: null,
    due_date: "2026-10-28",
    comments: [],
    status_history: [],
    assignee_history: [],
    ftt_section: "База знаний",
    cycle_hours: 2,
    type: "Ошибка",
    environment: "Прод",
    ...over,
  };
}

function view(over: Partial<RedmineView> = {}): RedmineView {
  return {
    connected: true,
    updated: true,
    message: "",
    issues: [],
    interval_minutes: 15,
    synced_at: "2026-10-30T09:00:00Z",
    next_sync_at: "2026-10-30T09:15:00Z",
    ...over,
  };
}

describe("Экраны зеркала Redmine", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRedmine.fetchMirror.mockResolvedValue({
      connected: false,
      updated: false,
      message: "",
      issues: [],
      interval_minutes: 15,
      synced_at: null,
      next_sync_at: null,
    });
    mockApi.listProjects.mockResolvedValue([]);
    mockApi.listSessions.mockResolvedValue([]);
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    })) as unknown as typeof window.matchMedia;
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("без подключения пишет, что Redmine ещё не подключён", async () => {
    mockRedmine.loadProject.mockResolvedValue({
      connected: false,
      updated: false,
      message: "Redmine ещё не подключён",
      issues: [],
      interval_minutes: 15,
      synced_at: null,
      next_sync_at: null,
    });
    renderAt("/office/7/redmine");
    expect(await screen.findByText("Redmine ещё не подключён")).toBeInTheDocument();
    expect(mockRedmine.loadProject).toHaveBeenCalledWith(7, "");
    expect(screen.queryByLabelText(/ключ/i)).not.toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/REDMINE_API_KEY|api_key/);
  });

  it("пустой проект: четыре экрана и кнопка создания, без задач", async () => {
    mockRedmine.loadProject.mockResolvedValue(view());
    renderAt("/office/7/redmine");
    expect(await screen.findByRole("button", { name: "Создать задачу" })).toBeInTheDocument();
    for (const label of ["Доска", "Список", "Аналитика", "Прогнозы"]) {
      expect(screen.getByRole("tab", { name: label })).toBeInTheDocument();
    }
    expect(screen.getByText("Задач нет")).toBeInTheDocument();
    expect(screen.queryByText("Redmine ещё не подключён")).not.toBeInTheDocument();
  });

  it("канбан: колонки по статусам со счётчиками", async () => {
    mockRedmine.loadProject.mockResolvedValue(view({
      issues: [
        issue({ id: 1, subject: "A", status: { id: "1", name: "Новая" } }),
        issue({ id: 2, subject: "B", status: { id: "1", name: "Новая" } }),
        issue({ id: 3, subject: "C", status: { id: "2", name: "В работе" } }),
      ],
    }));
    renderAt("/office/7/redmine");
    expect(await screen.findByRole("region", { name: "Новая" })).toBeInTheDocument();
    expect(screen.getByText("Новая · 2")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "В работе" })).toBeInTheDocument();
    expect(screen.getByText("В работе · 1")).toBeInTheDocument();
  });

  it("фильтр раздела убирает чужую задачу на доске, в списке, в аналитике и в прогнозах", async () => {
    mockRedmine.loadProject.mockResolvedValue(view({
      issues: [
        issue({ id: 15, subject: "Статья", ftt_section: "База знаний" }),
        issue({
          id: 16,
          subject: "Курс",
          ftt_section: "Управление электронным обучением",
          type: "Задача",
          assignee: { user_id: 8, login: "boris", name: "Борис" },
          status: { id: "2", name: "В работе" },
          cycle_hours: null,
        }),
      ],
    }));
    renderAt("/office/7/redmine");
    expect(await screen.findByText("Курс")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Раздел функциональных требований"), {
      target: { value: "База знаний" },
    });
    expect(screen.queryByText("Курс")).not.toBeInTheDocument();
    expect(screen.getByText("Статья")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Список" }));
    expect(screen.getByText("Статья")).toBeInTheDocument();
    expect(screen.queryByText("Курс")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Аналитика" }));
    expect(screen.getByRole("heading", { name: "Разрез по исполнителям" })).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /Анна/ })).toBeInTheDocument();
    expect(screen.queryByRole("row", { name: /Борис/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Прогнозы" }));
    expect(screen.getByText("Открытых задач нет")).toBeInTheDocument();
    expect(screen.queryByText("Курс")).not.toBeInTheDocument();
  });

  it("тип, окружение, статус, автор и исполнитель сужают доску", async () => {
    mockRedmine.loadProject.mockResolvedValue(view({
      issues: [
        issue(),
        issue({
          id: 16,
          subject: "Курс",
          type: "Задача",
          environment: "Тест",
          status: { id: "2", name: "В работе" },
          author: { user_id: 9, login: "olga", name: "Ольга" },
          assignee: { user_id: 8, login: "boris", name: "Борис" },
          cycle_hours: null,
        }),
      ],
    }));
    renderAt("/office/7/redmine");
    expect(await screen.findByText("Курс")).toBeInTheDocument();
    const checks: Array<[string, string]> = [
      ["Тип", "Ошибка"],
      ["Окружение", "Прод"],
      ["Статус", "Закрыта"],
      ["Автор", "Иван"],
      ["Исполнитель", "Анна"],
    ];
    for (const [label, value] of checks) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
      expect(screen.queryByText("Курс")).not.toBeInTheDocument();
      expect(screen.getByText("Статья")).toBeInTheDocument();
      fireEvent.change(screen.getByLabelText(label), { target: { value: "" } });
      expect(screen.getByText("Курс")).toBeInTheDocument();
    }
  });

  it("аналитика считает медиану часов исполнителя: 2 и 4 дают 3", async () => {
    mockRedmine.loadProject.mockResolvedValue(view({
      issues: [
        issue({ id: 15, cycle_hours: 2 }),
        issue({ id: 16, subject: "Вторая", cycle_hours: 4 }),
        issue({
          id: 17,
          subject: "Чужая",
          assignee: { user_id: 8, login: "boris", name: "Борис" },
          cycle_hours: null,
        }),
      ],
    }));
    renderAt("/office/7/redmine");
    fireEvent.click(await screen.findByRole("tab", { name: "Аналитика" }));
    const anna = screen.getByRole("row", { name: /Анна/ });
    expect(anna).toHaveTextContent("2");
    expect(anna).toHaveTextContent("3");
    expect(screen.getByRole("row", { name: /Борис/ })).toHaveTextContent("-");
  });

  it("прогноз открытой задачи берёт ориентир 8.8 из часов 2 и 10", async () => {
    mockRedmine.loadProject.mockResolvedValue(view({
      issues: [
        issue({ id: 15, cycle_hours: 2, ftt_section: "База знаний" }),
        issue({ id: 16, subject: "Закрытая", cycle_hours: 10, ftt_section: "База знаний" }),
        issue({
          id: 17,
          subject: "Курс",
          ftt_section: "База знаний",
          status: { id: "2", name: "В работе" },
          cycle_hours: null,
        }),
      ],
    }));
    renderAt("/office/7/redmine");
    fireEvent.click(await screen.findByRole("tab", { name: "Прогнозы" }));
    expect(screen.getByRole("row", { name: /Курс/ })).toHaveTextContent("8.8");
    expect(screen.queryByText("Статья")).not.toBeInTheDocument();
  });

  it("период 7 дней на 30.10.2026 прячет задачу от 1 октября", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-30T12:00:00Z"));
    mockRedmine.loadProject.mockResolvedValue(view({
      issues: [
        issue({ id: 15, subject: "Свежая", due_date: "2026-10-28" }),
        issue({ id: 16, subject: "Старая", due_date: "2026-10-01" }),
      ],
    }));
    renderAt("/office/7/redmine");
    expect(await screen.findByText("Старая")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Период"), { target: { value: "7" } });
    expect(screen.getByText("Свежая")).toBeInTheDocument();
    expect(screen.queryByText("Старая")).not.toBeInTheDocument();
  });

  it("правка карточки показывает описание, которое вернул сервер", async () => {
    const saved = issue({ description: "как в Redmine" });
    mockRedmine.loadProject.mockResolvedValue(view({
      issues: [issue({
        assignee: { user_id: 4, redmine_id: 9, login: "anna", name: "Анна" },
      })],
    }));
    mockRedmine.updateIssue.mockResolvedValue({ updated: true, issue: saved });
    renderAt("/office/7/redmine");
    fireEvent.click(await screen.findByRole("button", { name: /Статья/ }));
    fireEvent.change(screen.getByLabelText("Описание"), {
      target: { value: "ещё не подтверждено" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(await screen.findByLabelText("Описание")).toHaveValue("как в Redmine");
    expect(screen.queryByDisplayValue("ещё не подтверждено")).not.toBeInTheDocument();
    expect(mockRedmine.updateIssue).toHaveBeenCalledWith(
      7,
      15,
      expect.objectContaining({
        description: "ещё не подтверждено",
        assigned_to_id: 9,
      }),
    );
  });

  it("с контекстом префилла модалка не открывается", async () => {
    mockRedmine.loadProject.mockResolvedValue(view());
    mockRedmine.createIssue.mockResolvedValueOnce({
      updated: true,
      issue: issue({ id: 88, subject: "Из созвона", description: "решение" }),
    });
    render(
      <MemoryRouter initialEntries={["/office/7/redmine"]}>
        <Routes>
          <Route
            path="/office/:id/redmine"
            element={<RedmineScreens projectId={7} createPrefill={{
              subject: "Из созвона",
              description: "решение",
            }} />}
          />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Создать задачу" }));
    expect(screen.queryByRole("dialog", { name: "Новая задача" })).not.toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "#88" })).toBeInTheDocument();
    expect(mockRedmine.createIssue).toHaveBeenCalledWith(
      7,
      expect.objectContaining({ subject: "Из созвона", description: "решение" }),
    );
  });

  it("справочники из БД видны в модалке без задач", async () => {
    mockRedmine.loadProject.mockResolvedValue(view({
      lookups: {
        types: ["Frontend"],
        environments: ["Десктоп"],
        ftt_sections: ["База знаний"],
        statuses: [
          { id: "1", name: "Новая" },
          { id: "2", name: "В работе" },
        ],
        authors: ["Иван"],
        assignees: ["Анна Петрова"],
        people_by_name: { "Анна Петрова": 42 },
      },
    }));
    renderAt("/office/7/redmine");
    fireEvent.click(await screen.findByRole("button", { name: "Создать задачу" }));
    const dialog = await screen.findByRole("dialog", { name: "Новая задача" });
    fireEvent.change(within(dialog).getByLabelText("Статус"), { target: { value: "2" } });
    expect(within(dialog).getByRole("option", { name: "В работе" })).toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: "Анна Петрова" })).toBeInTheDocument();
  });

  it("создание: модалка, тема и вызов зеркала по токену сервера", async () => {
    mockRedmine.loadProject.mockResolvedValue(view());
    mockRedmine.createIssue.mockResolvedValueOnce({
      updated: true,
      issue: issue({ id: 77, subject: "Моя задача", description: "описание" }),
    });
    renderAt("/office/7/redmine");
    fireEvent.click(await screen.findByRole("button", { name: "Создать задачу" }));
    expect(await screen.findByRole("dialog", { name: "Новая задача" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Тема"), { target: { value: "Моя задача" } });
    fireEvent.change(screen.getByLabelText("Описание"), { target: { value: "описание" } });
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));
    expect(await screen.findByRole("heading", { name: "#77" })).toBeInTheDocument();
    const body = mockRedmine.createIssue.mock.calls[0][1] as Record<string, unknown>;
    expect(body).toMatchObject({
      subject: "Моя задача",
      description: "описание",
      redmine_project: "",
    });
    expect(body).not.toHaveProperty("api_key");

    mockRedmine.createIssue.mockRejectedValueOnce(
      new ApiError(502, '502 Bad Gateway: {"detail":"Redmine не вернул номер задачи"}'),
    );
    fireEvent.click(screen.getByRole("button", { name: "Закрыть карточку" }));
    fireEvent.click(screen.getByRole("button", { name: "Создать задачу" }));
    fireEvent.change(await screen.findByLabelText("Тема"), { target: { value: "Ещё одна" } });
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Redmine не вернул номер задачи");
    expect(screen.queryByRole("heading", { name: "#78" })).not.toBeInTheDocument();
  });

  it("заказчик не открывает экраны", async () => {
    mockRedmine.loadProject.mockRejectedValue(
      new ApiError(403, '403 Forbidden: {"detail":"Заказчик не открывает задачи Redmine"}'),
    );
    renderAt("/office/7/redmine");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Заказчик не открывает задачи Redmine",
    );
    expect(screen.queryByRole("tab", { name: "Доска" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Создать задачу" })).not.toBeInTheDocument();
  });

  it("нечисловой id не вызывает загрузку", () => {
    renderAt("/office/abc/redmine");
    expect(screen.getByText("Проект не найден")).toBeInTheDocument();
    expect(mockRedmine.loadProject).not.toHaveBeenCalled();
  });
});
