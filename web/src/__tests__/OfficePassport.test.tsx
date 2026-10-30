import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// Мастер паспорта: черновик переживает перезагрузку, платформа предлагает тип
// с одной фразой, двойное «Создать» отправляет один ключ идемпотентности.
const mockPassport = vi.hoisted(() => ({
  createProject: vi.fn(),
  suggestType: vi.fn(),
  setType: vi.fn(),
}));
vi.mock("@/components/office/passport/passportApi", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/components/office/passport/passportApi")>();
  return { ...actual, passportApi: mockPassport };
});

const mockOffice = vi.hoisted(() => ({
  listProjects: vi.fn(),
  getProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
}));
vi.mock("@/components/office/officeApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/office/officeApi")>();
  return { ...actual, officeApi: mockOffice };
});

import { MemoryRouter } from "react-router-dom";
import { ApiError } from "@/api/client";
import NewProjectButton from "@/components/office/passport/NewProjectButton";
import PassportTab from "@/components/office/passport/PassportTab";
import OfficeProjectList from "@/components/office/OfficeProjectList";

const SUGGESTION = {
  project_type: "small",
  reason: "Сайт на заказ укладывается в паспорт, бриф и задачи без бюджета и графика.",
};

function openWizard(onCreated = vi.fn()) {
  const view = render(<NewProjectButton onCreated={onCreated} />);
  fireEvent.click(screen.getByRole("button", { name: "Новый проект" }));
  return { ...view, onCreated };
}

function fillPassport() {
  fireEvent.change(screen.getByLabelText("Название"), { target: { value: "Сайт пекарни" } });
  fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "site" } });
  fireEvent.change(screen.getByLabelText("Характер"), { target: { value: "custom" } });
}

describe("Мастер паспорта проекта", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockPassport.suggestType.mockResolvedValue(SUGGESTION);
  });

  it("черновик паспорта дописывается после перезагрузки страницы", () => {
    const first = openWizard();
    fillPassport();
    first.unmount();

    openWizard();
    expect(screen.getByLabelText("Название")).toHaveValue("Сайт пекарни");
    expect(screen.getByLabelText("Вид работ")).toHaveValue("site");
    expect(screen.getByLabelText("Характер")).toHaveValue("custom");
  });

  it("платформа предлагает тип одной фразой, менеджер соглашается", async () => {
    openWizard();
    fillPassport();
    expect(await screen.findByText(SUGGESTION.reason)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Согласиться: маленький" }));
    expect(screen.getByRole("radio", { name: "Маленький" })).toBeChecked();
  });

  it("двойное «Создать» отправляет один запрос с ключом и чистит черновик", async () => {
    let resolve!: (v: unknown) => void;
    mockPassport.createProject.mockReturnValue(new Promise((r) => (resolve = r)));
    const { onCreated } = openWizard();
    fillPassport();
    const create = screen.getByRole("button", { name: "Создать" });
    fireEvent.click(create);
    fireEvent.click(create);
    expect(mockPassport.createProject).toHaveBeenCalledTimes(1);
    const body = mockPassport.createProject.mock.calls[0][0];
    expect(body).toMatchObject({ name: "Сайт пекарни", work_kind: "site", nature: "custom" });
    expect(body.request_key).toBeTruthy();
    // Тип не выбран: проект создаётся черновиком, умолчание не подставляется.
    expect(body.project_type).toBe("");
    resolve({ id: 42 });
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(42));
    expect(localStorage.length).toBe(0);
  });
});

const DRAFT_PROJECT = {
  id: 7, name: "Сайт пекарни", work_kind: "site", nature: "custom",
  description: "Лендинг", project_type: "", status: "draft",
};

describe("Вкладка «Паспорт»", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPassport.suggestType.mockResolvedValue(SUGGESTION);
  });

  it("без типа проект не стартовал, и страница говорит это словами", async () => {
    const onChange = vi.fn();
    const started = { ...DRAFT_PROJECT, project_type: "small", status: "active" };
    mockPassport.setType.mockResolvedValue(started);
    render(<PassportTab project={DRAFT_PROJECT} onProjectChange={onChange} />);
    expect(screen.getByText(/Черновик: тип проекта не выбран/)).toBeInTheDocument();
    expect(screen.getByText("Сайт")).toBeInTheDocument();
    expect(screen.getByText("Заказ")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Согласиться: маленький" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить тип" }));
    await waitFor(() => expect(mockPassport.setType).toHaveBeenCalledWith(7, "small"));
    expect(onChange).toHaveBeenCalledWith(started);
  });

  it("смена типа после принятого задания показывает отказ сервера", async () => {
    mockPassport.setType.mockRejectedValue(
      new ApiError(409, "409 Conflict: Тип нельзя сменить: заказчик уже принял версию задания"),
    );
    const project = { ...DRAFT_PROJECT, project_type: "small", status: "active" };
    render(<PassportTab project={project} onProjectChange={vi.fn()} />);
    expect(screen.queryByText(/Черновик/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Крупный" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить тип" }));
    expect(await screen.findByText(/заказчик уже принял версию задания/)).toBeInTheDocument();
  });
});

describe("Список проектов листается", () => {
  it("«Показать ещё» догружает следующую страницу", async () => {
    const page = (from: number, n: number) =>
      Array.from({ length: n }, (_, i) => ({
        ...DRAFT_PROJECT, id: from + i, name: `Проект ${from + i}`,
      }));
    mockOffice.listProjects
      .mockResolvedValueOnce(page(1, 21))
      .mockResolvedValueOnce(page(21, 3));
    render(
      <MemoryRouter>
        <OfficeProjectList />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("link", { name: "Проект 20" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Проект 21" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));
    expect(await screen.findByRole("link", { name: "Проект 23" })).toBeInTheDocument();
    expect(mockOffice.listProjects).toHaveBeenLastCalledWith({ offset: 20, limit: 21 });
    expect(screen.queryByRole("button", { name: "Показать ещё" })).not.toBeInTheDocument();
  });

  it("в строке есть открыть, переименовать и удалить", async () => {
    mockOffice.listProjects.mockResolvedValue([
      { ...DRAFT_PROJECT, id: 5, name: "вапвап" },
    ]);
    render(
      <MemoryRouter>
        <OfficeProjectList />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("link", { name: "вапвап" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть" })).toHaveAttribute("href", "/office/5");
    expect(screen.getByRole("button", { name: "Переименовать" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Удалить" })).toBeInTheDocument();
  });
});
