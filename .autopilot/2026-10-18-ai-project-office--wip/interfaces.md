# Границы

Скопировано из спецификации и дополнено решениями, которые записаны в её тексте позже таблицы. Если таблица в `spec.md` короче этого файла, верен этот файл.

## Правила для следующей сборки

- Код: репозиторий `AI-Workspace`, ветка `develop`. Стек уже есть: Python 3.11+, FastAPI, React 19, Vite, Tailwind, SQLite.
- Не создавать второе приложение рядом.
- Секреты не писать в файлы и не коммитить. Имена переменных только в `.env.example`.
- Тесты бэкенда: `.venv/bin/python -m pytest tests -q`. Тесты фронта: `cd web && npx vitest run`.
- Шов приёмки: публичные операции модуля `cycle`. Не ставить отдельный тест на внутренности, если поведение видно через `cycle`.
- Нет зависимости, без которой нельзя продолжить: статус `BLOCKED`, не установка наугад.
- Этот прогон код не пишет. Сборка начинается со среза A в `plan.md`, и только когда пользователь просит собрать.

## Границы

| Модуль | Владеет | Выставляет | Прячет |
|---|---|---|---|
| `tenancy` | Компания, пользователи, роли, три рабочих места, видимость документов, политика записи, ключи моделей | `invite`; `setRecordingPolicy`; `setModelRoute`; `setVisibility` | Хранение ключа, списание лимита |
| `project` | Паспорт, тип маленький или крупный, вид работ, бриф, участники | `createProject`; `setType` | Текст предложения типа |
| `cycle` | Требования, версии задания, трассировка, маршруты согласования, задачи, согласия, риски | `draftSpec`; `comment`; `approveStep`; `acceptSpec`; `approveTask`; `handToTeam` | Кто обязателен в цепочке, если роль назначена |
| `plan` | Дерево работ, оценки, бюджет, диаграмма Ганта, база, освоенный объём. На экране только у крупного типа | `saveBaseline`; `earnedValue` | Формула освоенного объёма |
| `knowledge` | Версии Markdown, поиск, граф Doublefy, диаграмма графа | `ingest`; `search`; `graph`; `export` | Разбор входных файлов. Word, PDF, Excel, Google Sheets собираются на экспорте и не хранятся как второй оригинал |
| `agents` | Запуски, черновики, библиотека скилов, планировщик, встроенный браузер | `assign`; `schedule`; `drafts` | Вызова «опубликовать заказчику» нет |
| `channels` | Почта, календарь, план дня, созвоны, планёрка, сигналы | `connectMailbox`; `placeMeeting`; `ingestMeeting`; `notify` | Адреса внешних каналов |
| `delivery` | Репозиторий, коммиты, макеты, прототип созвона, прогоны, сценарии из демонстраций, руководство, ролик | `linkRepo`; `openMerge`; `runCheck`; `saveDemoAsTest`; `renderGuide`; `renderDemo` | Номер тикета в сообщении коммита, Pen.dev, Playwright |
| `insight` | Дашборды здоровья проекта и портфеля | `buildDashboard`; `companySnapshot` | Какие числа роль имеет право видеть |
| `bridge` | Библиотека подключений: Jira, Confluence, Bitrix24, Redmine, Яндекс.Трекер, видеосвязь, IP-телефония, электронный документооборот | `connect`; `pushAccepted`; `pushAgreedDocument` | Протокол внешней системы |

Шов для тестов один: публичные операции `cycle`.

## Решения плана, срез A

Решения этого прогона, не спецификации. Таски читают их перед кодом.

- Код офиса: пакет `src/office/` с подпакетами по границам `tenancy`, `project`, `cycle`, `knowledge`, `agents`. Границы `plan`, `channels`, `delivery`, `insight`, `bridge` в срезе A не создаются.
- Хранилище: та же SQLite-база, что у чатов (`SESSION_DATABASE_PATH`). Таблицы с префиксом `office_`. Схему создаёт при старте отдельный модуль хранения офиса, идемпотентно. `SessionManager` не расширять.
- Маршруты: `/api/office/...`. По файлу на границу: `src/web/routes_office.py` (общие зависимости и монтирование), `routes_office_project.py`, `routes_office_brief.py`, `routes_office_spec.py`. Фабрика роутера и зависимости авторизации как у остальных роутеров приложения.
- Фронт: страницы `/office` и `/office/:id` в `web/src/routes/OfficePage.tsx`. Компоненты по вкладкам в `web/src/components/office/<вкладка>/`. Клиент API каждой вкладки лежит в папке своей вкладки `web/src/components/office/<вкладка>/` и пользуется `officeRequest` из `web/src/components/office/officeApi.ts` (уточнено после таска 01); общий `web/src/lib/types.ts` не трогать. Markdown рисует существующий `web/src/lib/Markdown.tsx`.
- Проекты офиса и «проекты» текущего приложения (папки с кодом для Claude) это разные сущности. Связь с репозиторием придёт в срезе E.
- Канон версии документа: текст Markdown в таблице версий. Файл `.md` на диске, поиск и граф Doublefy: срез C.
- Модель: через Claude Agent SDK теми же учётными данными, что чат (ключ пользователя из `src/apikeys`, иначе подписка платформы). Пакет `anthropic` не добавлять, ключ не спрашивать, новых переменных окружения не заводить. Маршрут по умолчанию одной константой в `agents`.
- Тесты: `tests/office/` на временной SQLite. Таски 02 и 03 тестируют свои роутеры; таск 04 ведёт сквозной путь через `cycle.draftSpec` с подменённым агентом. Фронт: `web/src/__tests__/Office*.test.tsx`.
- Таски одной волны не редактируют общие файлы: `src/web/server.py`, `src/web/routes_office.py`, `web/src/App.tsx`, `web/src/routes/OfficePage.tsx`, `web/src/components/Sidebar.tsx`, `web/src/lib/types.ts`. Каркас создаёт таск 01; каждый следующий таск пишет только в свою зону.
- Код по правилам `karpathy-coding`: минимум кода под задачу, точечные правки, соответствие стилю соседнего кода, тест как критерий готовности. Длинное тире в тексте интерфейса и документах не использовать.

## Из таска 01 — каркас офиса

- Хранилище `OfficeStore(db_path)` в `src/office/storage.py`, одна база с чатами; `WebServer.office_store` создаётся на `session_manager.storage_path`. Операции: `create_project(*, name, created_by, work_kind='', nature='', project_type='small', status='active') -> dict`; `get_project(id)`; `list_projects()`; `list_projects_for_user(user_id)`; `update_project(id, **поля паспорта: name, work_kind, nature, project_type, status)`; `add_member(project_id, user_id, role)` (повтор меняет роль); `get_member`; `list_members`; `ensure_document(project_id, kind)` / `get_document`; `add_version(document_id, *, markdown, source, status='draft', created_by=None)` (number = max+1); `get_version`; `list_versions`; `latest_version`; `set_version_status(version_id, status)`; `close()`.
- Таблицы: `office_projects(id, name, work_kind, nature, project_type, status, created_by, created_at, updated_at)`, `office_members(project_id, user_id, role, added_at; PK project_id+user_id)`, `office_documents(id, project_id, kind; UNIQUE project_id+kind)`, `office_document_versions(id, document_id, number, status, source, markdown, created_by, created_at; UNIQUE document_id+number)`. Статусы версии и виды документов (`brief`, `spec`) хранилище не проверяет: это дело границ `cycle` и `knowledge`.
- `tenancy` (`src/office/tenancy/`): `ROLES` (ключ -> русское название, 11 ролей по спецификации), `MANAGER = 'project_manager'`, `visible_projects(store, *, actor_id, is_admin)`, `open_project(store, project_id, *, actor_id, is_admin) -> dict | None`, `record_creator(store, project_id, user_id)` (создатель = менеджер).
- Границы `project`, `cycle`, `knowledge`, `agents`: пустые `__init__` с `__all__ = []`. Публичные операции выставлять из `__init__`, внутренности в `_*.py`.
- API: `GET /api/office/projects` (видимые актору), `GET /api/office/projects/{id}` (чужой и несуществующий: 404 с `detail`). Фабрики `make_office_project_router` / `make_office_brief_router` / `make_office_spec_router(*, office_store, require_actor, require_project) -> APIRouter` без префикса (родитель даёт `/api/office`); `require_actor -> {user_id, is_admin}`; `require_project(project_id) -> {actor, project}`. Роутер офиса монтируется, только если у `session_manager` есть `storage_path`.
- Фронт: `web/src/components/office/officeApi.ts`: `officeApi.listProjects()`, `officeApi.getProject(id)`, `officeRequest<T>(method, path, body?)`, тип `OfficeProject`. Заглушки: `passport/NewProjectButton {onCreated(id)}` (пока disabled, создание делает таск 02), `passport/PassportTab {project, onProjectChange(project)}`, `brief/BriefTab {project}`, `spec/SpecTab {project}`. Маршруты `/office`, `/office/:id` под `Protected`; ссылка «Проектный офис» в Sidebar.
- Тесты: `tests/office/` (schema, storage, access); фронт `web/src/__tests__/Office*.test.tsx`.

## Уточнения после ревью таска 01

- Один писатель на таблицу. `project` пишет `office_projects` и `office_members`. `knowledge` единственный пишет `office_documents` и `office_document_versions` (бриф и задание одинаково: версия Markdown). `cycle` владеет статусами версии задания (`черновик → отправлено заказчику → принято | возвращено`, принятая не меняется) и меняет статус только через операцию `knowledge`, автомат переходов живёт в `cycle`. Роутер брифа (таск 03) и роутер задания (таск 04) ходят в хранилище только через `knowledge` и `cycle`, не через `OfficeStore` напрямую.
- `office_documents` имеет ещё колонку `created_at`.
- Тип проекта в хранилище пустой (`''`) до явного выбора человека; умолчание `'small'` в `create_project` выбором не считается. Таск 02 правит умолчания паспорта в `src/office/storage.py` (его зона в волне 2; таск 03 этот файл не трогает).
- Два `GET /api/office/projects*` из `routes_office.py` таск 02 может перенести в `routes_office_project.py`, чтобы паспорт жил в одном файле; `routes_office.py` остаётся общими зависимостями и монтированием.
- Два источника администратора (`users.is_admin` и роль участника `system_admin`, которую `open_project` не учитывает): в срезе A источник один, флаг `users.is_admin`; роль `system_admin` участнику не назначать. Исправление в `tenancy` отложено в concerns.
- Исключение участника из проекта (строка «Доступ», колонка «После») приходит вместе с `invite` и `setVisibility` в следующем срезе.
- Тесты внутренностей `OfficeStore` допущены только в таске 01; с таска 04 поведение документов и версий проверяется через `cycle.draftSpec`, не дублируется на уровне хранилища.
- `ruff check src/` даёт 92 старые ошибки вне офиса; критерий «ruff чист» для тасков значит: новые и изменённые файлы офиса чистые, остальное не трогать.
