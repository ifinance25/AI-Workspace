# Границы

Скопировано из спецификации и дополнено решениями, которые записаны в её тексте позже таблицы. Если таблица в `spec.md` короче этого файла, верен этот файл.

## Правила для следующей сборки

- Код: репозиторий `AI-Workspace`, ветка `develop`. Стек уже есть: Python 3.11+, FastAPI, React 19, Vite, Tailwind, SQLite.
- Не создавать второе приложение рядом.
- Секреты не писать в файлы и не коммитить. Имена переменных только в `.env.example`.
- Тесты бэкенда: `.venv/bin/python -m pytest tests -q`. Тесты фронта: `cd web && npx vitest run`.
- Шов приёмки: публичные операции модуля `cycle`. Не ставить отдельный тест на внутренности, если поведение видно через `cycle`.
- Нет зависимости, без которой нельзя продолжить: статус `BLOCKED`, не установка наугад.
- Код пишется только по команде пользователя. Разработка остановлена 2026-10-22 словом пользователя («Останови разработку кодов в том положении, которое есть сейчас. Ничего не удаляй.»): таски 01 и 03 в коммитах, таск 02 в рабочей папке без коммита, таск 04 не начат. При продолжении порядок тасков по `plan.md`.

## Границы

| Модуль | Владеет (единственный писатель) | Ключевые операции | Зависит от |
|---|---|---|---|
| `core` | `office_events`, `office_audit`, `office_jobs`, `office_schema_version`; миграции, соединения | `transaction`, `emit`, `enqueue`, `audit` | нет |
| `tenancy` | Компания, подразделения, `office_company_users` (сторона `executor` или `customer`), организации заказчика, профили видимости, политика записи, `office_credentials`, `office_model_routes`, `office_limits` | `invite`, `set_visibility`, `set_recording_policy`, `set_model_route`, `set_limit`, `put_credential`, `model_credential`, `scope`, `can`, `open_project` | `core` |
| `routing` | `office_usage`, `office_usage_reservations`; транспорт `ClaudeBridge` | `resolve`, `reserve`, `settle`, `call`, `usage` | `tenancy` |
| `knowledge` | Документы, версии, абзацы; `office_doc_repos`, `office_doc_branches`, `office_doc_commits`, `office_git_intents`; источники, квитанции, фрагменты, `office_embedding_cache`, `office_vectors`, индекс слов, граф Doublefy, эпоха, качество | `ingest`, `ingest_file`, `ingest_source`, `has_version`, `set_version_status`, `open_branch`, `commit_to_branch`, `merge_branch`, `close_branch`, `import_agent_commits`, `restore_version`, `revert_merge`, `diff`, `search`, `ask`, `verify_quote`, `graph`, `export`, `reindex`, `index_status` | `routing` |
| `bridge` | `office_bridge_connections`, `_links`, `_outbox`, `_cursor`; среда коннекторов; адаптеры трекера, вики, документооборота | `connect`, `check`, `disconnect`, `push_accepted`, `register_adapter` | `knowledge` |
| `project` | `office_projects`, `office_memberships`, `office_type_changes` | `create_project`, `set_type`, `request_type_change`, `add_member`, `remove_member` | `knowledge` |
| `cycle` | Требования, кандидаты, улики, противоречия, дубли, след, маршруты, MR и ревью документов, обсуждения, комментарии, публикации, задачи, спринты, согласия, риски, решения, обещания, ролевая модель | `draft_spec`, `open_doc_mr`, `submit_doc_mr`, `review_doc_mr`, `merge_doc_mr`, `revert_doc_mr`, `rollback_document`, `start_route`, `approve_step`, `return_step`, `accept_spec`, `publish`, `propose_requirements`, `decide_candidate`, `resolve_conflict`, `trace_matrix`, `confirm_trace`, `requirement_card`, `change_preview`, `slice_tasks`, `approve_task`, `hand_to_team` | `project`, `bridge` |
| `plan` | `office_wbs_items`, `office_estimates`, `office_baselines` | `save_baseline`, `earned_value` (D06) | `cycle` |
| `contracts` | `office_contract_templates`, `office_questionnaires` (тексты договоров у `knowledge`) | `fill_questionnaire`, `draft_addendum` | `plan` |
| `delivery` | Подключение кода, коммиты и MR кода, макеты, сценарии, прогоны, сверки; адаптеры GitHub, GitLab | `link_repo`, `record_commit`, `open_code_mr`, `merge_code_mr`, `run_check`, `render_guide` | `cycle` |
| `channels` | Созвоны, встречи, `office_mailbox_connections`, уведомления; адаптеры видеосвязи, телефонии, почты, календарей | `place_meeting`, `ingest_meeting`, `finalize_call`, `connect_mailbox`, `bind_mailbox_folder`, `notify` | `cycle` |
| `insight` | `office_dashboards`, `office_metric_snapshots` | `build_dashboard`, `project_health` | `plan`, `contracts`, `delivery`, `channels` (чтение) |
| `agents` | `office_agent_runs`, `_run_log`, `_drafts`, `_schedules`, `office_skills`, `_skill_versions`, `_skill_enablements`, `office_solutions` | `assign`, `schedule`, `rollback_run`, `pause_agents`, `enable_skill`, `import_skill`; метода «опубликовать» нет | `insight` и ниже |
| `ui` | Таблиц нет | HTTP, WebSocket, MCP, три рабочих места | все |

Таблица 2026-10-22 приведена к 14 модулям `architecture/05-sverka-superarhitektora.md`, §3.1 и §3.7 (при расхождении верен 05). Зависимость только вниз, вверх только события и задания `core`; все зовут `core` и `tenancy`. Имена операций `snake_case`, прежние camelCase их синонимы. Швы с подделкой для тестов: `DocRepo`, `VectorIndex`, `Embedder`, `JobQueue`, `ModelGateway` (`routing`), `BlobStore`.

Шов для тестов один: публичные операции `cycle`. Отдельный тест `knowledge` допускается для `reindex`, `index_status`, `DocRepo` (обрыв в каждом окне записи) и `import_agent_commits`; `traceMatrix(project, actor)` отдаёт матрицу, уже отфильтрованную по правам.

## Решения плана, срез A

Решения этого прогона, не спецификации. Таски читают их перед кодом.

- Код офиса: пакет `src/office/` с подпакетами по границам `tenancy`, `project`, `cycle`, `knowledge`, `agents`. Границы `plan`, `channels`, `delivery`, `insight`, `bridge` в срезе A не создаются.
- Хранилище: та же SQLite-база, что у чатов (`SESSION_DATABASE_PATH`). Таблицы с префиксом `office_`. Схему создаёт при старте отдельный модуль хранения офиса, идемпотентно. `SessionManager` не расширять.
- Маршруты: `/api/office/...`. По файлу на границу: `src/web/routes_office.py` (общие зависимости и монтирование), `routes_office_project.py`, `routes_office_brief.py`, `routes_office_spec.py`. Фабрика роутера и зависимости авторизации как у остальных роутеров приложения.
- Фронт: страницы `/office` и `/office/:id` в `web/src/routes/OfficePage.tsx`. Компоненты по вкладкам в `web/src/components/office/<вкладка>/`. Клиент API каждой вкладки лежит в папке своей вкладки `web/src/components/office/<вкладка>/` и пользуется `officeRequest` из `web/src/components/office/officeApi.ts` (уточнено после таска 01); общий `web/src/lib/types.ts` не трогать. Markdown рисует существующий `web/src/lib/Markdown.tsx`.
- Проекты офиса и «проекты» текущего приложения (папки с кодом для Claude) это разные сущности. Связь с репозиторием придёт в срезе E.
- Канон версии документа: текст Markdown в таблице версий. Файл `.md` на диске, поиск и граф Doublefy: срез C. Заменено 2026-10-22 со среза B: две равные копии (таблица и внутренний Git), зеркала `.md` нет, см. «Решения архитектуры 2026-10-22».
- Модель: через Claude Agent SDK теми же учётными данными, что чат (ключ пользователя из `src/apikeys`, иначе подписка платформы). Пакет `anthropic` не добавлять, ключ не спрашивать, новых переменных окружения не заводить. Маршрут по умолчанию одной константой в `agents`. Заменено 2026-10-22: ключ только через `routing` и `tenancy.model_credential` (таск 05), см. «Решения архитектуры 2026-10-22».
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

## Уточнения после штурма 2026-10-21 (спецификация дополнена 2026-10-22)

Источник: `spec.md`, разделы «Ядро: хранилище контекста и след требований» и «Ядро: решения по реализации»; `brainstorm-2026-10-21.md`. Таски читают это перед кодом.

- Строки `knowledge` и `cycle` в таблице «Границы» заменены. Правило «один писатель на таблицу» сохраняется: `knowledge` пишет источники, квитанции, фрагменты, индексы, граф, карту абзацев, задания индексации, обратную связь и золотой набор; `cycle` пишет требования и их версии, кандидатов, улики, противоречия и ссылки следа. Чтение чужих таблиц только через публичные операции границы.
- Таск 03 (бриф): при создании версии `knowledge` присваивает каждому абзацу устойчивый идентификатор (отпечаток нормализованного текста плюс порядковый номер среди одинаковых) и хранит его рядом с версией; между соседними версиями одного документа строится карта абзацев (совпал, изменён, переехал, удалён, новый; порог схожести 0,6). Форма хранения (таблица карты или JSON у версии) за исполнителем, писатель один: `knowledge`. Комментарии среза B якорятся на эти идентификаторы.
- Таск 04 (черновик задания): каждый нумерованный пункт функциональных требований несёт невидимый маркер `<!-- req:REQ-NNN -->` и строку «Источник: бриф v<N>, абзац <id>» с дословной цитатой из брифа. Цитата проверяется посимвольно без модели; пункт без найденной цитаты помечается «предположение модели». Ключ `REQ-NNN` не зависит от номера в списке и от версии задания. Таблица требований в `cycle` в срезе A минимальная: ключ, формулировка, версия задания, идентификатор абзаца брифа, статус кандидат или подтверждено. Это углубление G104 и G112 (история 52), не новая возможность.
- Виды документов: грамматика `семейство[:ключ]` поверх существующего ограничения «один документ на вид в проекте». В срезе A используются `brief` и `spec`.
- Роли: `HANDOFF.md` и спецификация называют тимлида и технического лида; таблицы ролей и меню спецификации дополнены. `tenancy.ROLES` (11 ролей) в срезе A не меняется; две роли добавляются в срезе E вместе с репозиторием. Долг записан.
- Межпроектный контекст: в запрос к модели для одного проекта никогда не попадают фрагменты другого проекта. `knowledge.search(project, actor, query)` принимает проект и актора; межпроектный поиск только по ядрам документов и только для акторов с доступом к обоим проектам (срез C, и только если пользователь не выключит его ответом на P04 из `brainstorm-2026-10-21.md`).
- Поставщик эмбеддингов: настройка компании, значение не задано до ответа пользователя; в срезе A не нужен (поиск появляется в срезе C). Векторное хранилище за интерфейсом `VectorIndex`: sqlite-vec с зафиксированной версией, запасной LanceDB. Без поставщика поиск работает по словам и графу.
- Код коммитов (срез E): сканер секретов до индексации, изменения по файлам, откат коммита удаляет фрагменты.
- Вопросы P01-P23 из `brainstorm-2026-10-21.md` в код не переносятся до ответа пользователя. Таски 02 и 03 волны 2 этим не блокируются. Ответ получен 2026-10-22 («пакет»): см. раздел «Решения пакета 2026-10-22» ниже.

## Из таска 03 — бриф проекта

- `knowledge.ingest(store, project_id, *, kind, markdown, source, created_by=None) -> {"version": {id, number, status, source, created_at}, "created": bool}`; повтор текста последней версии даёт `created=False`
- `knowledge.ingest_file(store, project_id, *, kind, filename, data, created_by=None)` -> то же; `source` = имя файла
- `knowledge.IngestError(code, message)`, code: `empty | unsupported | unreadable`; `knowledge.ACCEPTED = (".md", ".txt", ".docx")`; `knowledge.TEXT_SOURCE = "текст"`
- `knowledge.versions(store, project_id, kind) -> [summary]`; `knowledge.version(store, project_id, kind, number) -> {summary, markdown, paragraphs} | None`
- `knowledge.paragraphs(store, project_id, kind, number) -> [{id, text}] | None`; id: `p-<sha1[:12]>-<n>`
- `knowledge.paragraphMap = paragraph_map(store, project_id, kind, number) -> [{status, old_id, new_id, old_index, new_index, similarity}] | None`; сравнивает `number-1` и `number`; status: `same | moved | changed | removed | added`; порог 0,6; считается по запросу, не хранится
- Таблица `office_paragraphs(version_id PK -> office_document_versions.id, paragraphs JSON)`, писатель один: `knowledge`
- HTTP: `POST /api/office/projects/{id}/brief {text}`; `POST .../brief/file` (multipart `file`); 201 новая версия, 200 повтор; 400 пусто или не читается, 415 не тот тип, 413 больше `routes_files.MAX_UPLOAD_BYTES`; `GET .../brief/versions`; `GET .../brief/versions/{number}` (с paragraphs); чужой проект 404
- Фронт: `components/office/brief/briefApi.ts` {listVersions, getVersion, saveText, uploadFile}, `errorText(err)`; типы BriefVersion, BriefVersionFull, BriefParagraph
- Долг: `knowledge` пишет абзацы через приватные `OfficeStore._connection()` и `_lock`; хранилищу нужен публичный хук (storage.py вне зоны таска 03)

## Из таска 02 — паспорт проекта и выбор типа

- `project.create_project(store, passport, *, actor_id) -> dict`; passport = {name, work_kind, nature, description, project_type?, request_key?}; повтор `request_key` тем же автором отдаёт тот же проект
- `project.set_type(store, project_id, project_type, *, actor_id, is_admin) -> dict`; `project.suggest_type(*, work_kind, nature, description='') -> {project_type, reason}` (правило детерминированное, без модели: product → large; web_platform, mobile_app → large; site на заказ → small)
- `project.list_projects(store, *, actor_id, is_admin, offset=0, limit=50)`; `PAGE_LIMIT_MAX=200`; листание режет в памяти `tenancy.visible_projects`, SQL LIMIT нет (tenancy вне зоны)
- Словари: `WORK_KINDS {site, web_platform, mobile_app}`, `NATURES {custom, product}`, `TYPES {small, large}`; ошибки `PassportError`, `ProjectTypeError`, `TypeLockedError(ProjectTypeError)`, `TypeChangeForbiddenError(PermissionError)`
- HTTP: `GET /api/office/projects?offset&limit` (массив, limit 1..200); `POST /api/office/projects` → 201, 422 при неверном паспорте; `GET /api/office/projects/{id}`; `POST /api/office/type-suggestion`; `PUT /api/office/projects/{id}/type {project_type}` → 200 | 403 (не менеджер и не админ) | 404 (чужой) | 409 (есть принятая версия задания) | 422
- storage: колонки `office_projects.description`, `create_key` (ALTER при старте для старой базы), уникальный индекс `(created_by, create_key)`; умолчания `create_project`: `project_type=''`, `status='draft'`; выбор типа переводит draft в active
- Запрет смены типа читает версии `spec` напрямую через OfficeStore, статус сравнивается с `project/_type.py: SPEC_ACCEPTED = "accepted"`. Таск 04 (`cycle`): выставить публичную проверку «есть принятая версия» и перевести `project` на неё
- Проект создаёт любой вошедший, создатель становится менеджером; тип меняют менеджер и админ
- Фронт: `components/office/passport/passportApi.ts` {createProject, suggestType, setType}; `officeApi.listProjects(page?: {offset, limit})`; `OfficeProject.description?`; черновик мастера в localStorage под ключом `office.passportDraft`

## Решения пакета 2026-10-22

Слова пользователя: «пакет» (бриф, 2026-10-22). Здесь только то, что меняет границы модулей и код. Полная таблица P01-P23: `spec.md`, «Решения пакета 2026-10-22». Первый выпуск это срезы A-E; отложенное (D01-D06) не строится, но и не закрывается в коде так, чтобы потом пришлось ломать границу.

- **P02, ключ модели (открыто до юриста, таск среза B).** Агент получает ключ только через `tenancy`: `tenancy.modelCredential(project) -> credential`, поиск по цепочке проект, подразделение, компания. Ключ пользователя из `src/apikeys` и подписка физлица агентом проекта не используются. Решение среза A («ключ пользователя, иначе подписка платформы») заменяется в срезе B; вызывающие `agents` не знают, откуда ключ. Значение ключа в API и в лог не отдаётся.
- **P04, D01, межпроектные связи.** В срезах A-G `knowledge` межпроектных рёбер не строит. `knowledge.search(project, actor, query)` никогда не выходит за `project`. Когда появится: настройка компании `crossProjectLinks`, по умолчанию выключена, меняет только админ; рёбра только между ядрами документов; каждый межпроектный запрос проверяет доступ актора к обоим проектам и пишется в журнал.
- **P05, D02, почта (заменено A19).** Алиаса проекта нет. `channels.connect_mailbox(owner, provider, credential) -> connection` для Яндекс 360, VK Workspace, Mail.ru, Google Mail (владелец пользователь или проект, секрет в `office_credentials` с областью `user` или `project`); `channels.bind_mailbox_folder(connection, folder, project)`; письмо из привязанной папки идёт `knowledge.ingest_source` вида `letter:<ключ из Message-ID>`, неоднозначное в «неразобранное». Ответ человек отправляет из своего подключённого ящика. Полный клиент не строится (D02).
- **P06, D06, подключения.** `bridge.connect(system, project)` в первом выпуске знает одну систему: трекер пилотных студий (выбор после P20). `bridge.pushAgreedDocument(version)` (документооборот) не строится. Набор остаётся открытым: новая система это новый адаптер за тем же `connect`.
- **P07, D05, слияние.** `delivery.merge(request, actor)` автоматически только если настройка проекта «авто», сборка зелёная и конфликтов нет; иначе запрос ждёт ручного слияния. У `agents.schedule` нет пути к `merge`: задача по расписанию код не сливает.
- **P22, коммиты.** `delivery.recordCommit(message)` связывает коммит с тикетом только по ключу с префиксом проекта (`ABC-12`, префикс в паспорте). Запросы на слияние агента идут от учётной записи бота компании с правом записи только в ветки агента; токен бота хранится как ключ модели, не в файлах.
- **P09, принятие версии.** Статус подписанта на маршруте называется «принято», операция `cycle.acceptSpec(version, actor)` без изменения сигнатуры; в интерфейсе слово «подпись» у версии не используется. Статус «подписано» есть только у договорных видов (`contract`, `addendum`, `act`) и ставится по квитанции подписанного документа извне.
- **P10, тип.** `project.setType(id, type, actor)`: маленький в крупный в любой момент, после согласования задания через шаг проектного офиса; крупный в маленький отказ после принятой базы.
- **P11, после сдачи.** Конечный прогон пишет новый вид документа `as_built`, а не новую версию `spec`; `spec` меняется только через маршрут `cycle`.
- **P12, D04, скилы.** `agents.importSkill(package) -> skill` сохраняет только текст инструкции, исполняемые файлы отбрасывает. Публикация в общую библиотеку `agents.publishSkill(skill, actor)` только админом после ручной очистки.
- **P13, D03, дашборд.** `insight.buildDashboard(actor, phrase)` переводит фразу в тройку (метрика, разрез, период) из фиксированного каталога; запрос к данным не генерируется. В каталоге метрика «путь требования» (история 59).
- **P14, P15, сверка.** `delivery.runCheck(task)` по макету: структурно (элементы, тексты, роли); визуальное расхождение только подсказка и не красит итог; макет привязан к версии требования, устаревший даёт `skipped`. Пункт ролевой модели рождается `предложено`, в сверку идёт после принятия системным аналитиком или менеджером.
- **P17, P18, созвон.** Тикеты кнопки после созвона создаются `черновик`; `cycle.approveTask` не переводит их в «ждёт согласия», пока версия задания не принята. Расшифровка у заказчика только после явной публикации менеджером; `traceMatrix` для заказчика отдаёт статус требований без названий задач.
- **P19, планировщик.** `agents.schedule(agent, rule)`: интервал не меньше суток; отдельная доля лимита; расписание снимается при исключении автора; до включения отдаёт три ближайших запуска в часовом поясе пользователя.
- **P23, P01, браузер и стенд.** Встроенный браузер принимает только адреса стенда проекта и запускается для агента, с изолированным профилем на запуск. Адрес стенда и учётные записи ролей лежат в настройках проекта как секреты (как ключи моделей), разворачивает стенд внешний CI.
- **P03 (открыто до юриста).** Политика записи по умолчанию «только текст» в `tenancy.setRecordingPolicy`; согласие каждого участника пишется в журнал до старта записи; голосовые отпечатки не хранятся.
- **Новые возможности пакета и их границы.** Карточка требования (история 57) и превью правки (58): чтение `cycle.traceMatrix` и графа `knowledge`, своей таблицы нет. Пакет правок к задачам (61) и протокол созвона (64): кандидаты в `cycle` с цитатой и таймкодом, проверка цитаты та же, что у кандидата требования. Журнал запуска и откат (62): `agents` пишет журнал запуска; откат снимает только непринятые версии и черновики, созданные этим запуском, через операции `knowledge` и `cycle`. MCP-сервер (63): тонкий слой над API истории 25, токен пользователя, режим «только чтение» или «изменения», операции публикации заказчику нет. Договорной комплект (60): виды `contract`, `addendum`, `act` в `knowledge`, анкета читает паспорт `project`, задание `cycle` и базу `plan`.

## Решения архитектуры 2026-10-22

Источник: комплект `architecture/`; обязательны единые решения `architecture/05-sverka-superarhitektora.md`, раздел 3, при расхождении верны они. Основание: слова пользователя 2026-10-22 (бриф: остановка разработки и проектирование, Git документации A10-A15, ответы A16-A24). Ниже правила для кода; полный текст в `architecture/00`-`04`.

- **Канон текста: две равные копии.** Текст версии хранится колонкой `office_document_versions.markdown` и блобом Git, связаны `content_sha` (отпечаток `markdown`) и `blob_sha`. Номер (`max+1` при рождении) и статус только в базе. Это заменяет решение среза A «канон версии: текст Markdown в таблице версий» со среза B.
- **Версия = слияние MR.** Версия это коммит первой родительской цепочки `main`, изменивший один файл, плюс строка версии. В `main` пишут только слияние MR (`--no-ff`, `git merge-tree`, git 2.38+), прямая запись (`brief`, `page:*`, маленький тип без команды) и откат (`restore_version`, `revert_doc_mr`). Одна слитая правка = одна версия `draft`; коммиты ветки не версии. Squash и rebase запрещены, ветка обновляется слиянием `main`. Одобряется голова MR; автослияния документов нет.
- **Метка `accepted`.** Принятие ставит аннотированную метку `accepted/<doc>/v<N>`, подписанную ключом платформы; это не подпись (P09). Метка не двигается; откат даёт новую версию `draft`.
- **`office_git_intents`.** Журнал намерений, писатель `knowledge`: `repo`, `ref`, `old_sha`, `new_sha`, `kind`, `payload`, `state pending | applied | aborted`. Порядок: объекты Git; намерение `pending`; `update-ref` со старым значением (отказ: `aborted`, 409 `stale_head`); транзакция с версией, `office_doc_commits`, `main_head`, событием и `applied`. Восстановление при старте до приёма запросов и раз в минуту; все записи проекта под файловой блокировкой `DocRepo`. В `office_doc_commits` только применённые коммиты, без `state`.
- **Репозиторий и каталог данных.** `<данные>/office/git/<company>/<project>.git`, голый; каталог данных офиса (`office/git/`, `office/blobs/`, `office/media/`, `office/export/`) вне `PROJECTS_DIR` и `confine_root`. Без git-сервера, клона, push, зеркала, вебхуков (A15). Путь файла: вид `f` → `f.md`, `f:k` → `f/k.md`. Ветки `edit/<doc>/<user_id>-<n>`, `agent/<run_id>/<doc>`, `call/<call_id>/<doc>`, `import/<upload_id>/<doc>`; закрытая в `refs/closed/`.
- **Временный клон агента.** Агент получает клон своей ветки `agent/<run>/<doc>` в каталоге запуска; голый репозиторий в джейл не монтируется. `knowledge.import_agent_commits(run)` забирает коммиты через `refs/quarantine/<run>` с проверкой путей, автора и секретов. Агент не сливает; его вердикт ревью не одобрение. Зеркала `.md` для агента нет.
- **`Embedder`.** Шов `Embedder` (`kind local | external`), умолчание локальная bge-m3; внешний включает только админ компании с записью в аудит; проект «запрет вывоза» остаётся на локальной; смена поставщика это фоновая переиндексация, пороги по `model_tag`. Векторы: `office_embedding_cache` (вектор один раз на `(model_tag, text_hash)`), `office_vectors` (строка на фрагмент с метаданными прав для фильтра внутри KNN). Распознавание речи устроено так же (A24).
- **События.** `core.emit` пишет в `office_events` в транзакции изменения; имена `<сущность>.<событие>` (`member.added`, `member.removed`, `docmr.conflict_detected`, `version.repo_mismatch`, `codemr.automerge_refused`, `agents.paused`, `usage.threshold` и каталог `architecture/03`, §6); в шину один тип `OfficeEvent`; браузер читает через `/api/office/ws` с `last_seq`; обработчики идемпотентны по `(name, seq)`. `office_audit` отдельно, с цепочкой отпечатков. Одна очередь `office_jobs`, отдельный процесс заданий офиса.
- **`routing` и ключ компании.** Каждый вызов модели через `routing`: `resolve`, `reserve`, `call`, `settle`, `usage`; сверх лимита 429 `limit_exhausted`. `routing.call` до замера на P20 идёт через `ClaudeBridge` (Agent SDK, `max_turns=1`, без инструментов); пакет `anthropic` не добавляется. Ключ только `tenancy.model_credential(project)` по цепочке проект, подразделение, компания; `src/apikeys` и подписка физлица агентом офиса не используются; ключ в джейл подставляет прокси `routing`. Секреты в `office_credentials` (`scope company | department | project | user`, `kind model_api_key | git_bot_token | webhook_secret | stand_account | connector_secret`), шифрование `SecretBox` мастер-ключом `CONNECTIONS_SECRET_KEY`.
- **Джейл для чатов (A23).** Каждая сессия чата Claude Code, включая админа и белый список, идёт в джейле и видит только свои проекты; база офиса, Git документации и каталог данных офиса не монтируются. Без bubblewrap установщик отказывает, по явному выбору админа ставит веб без чата. Агенты офиса: своя ветка моста с `require_jail=True`, своё сетевое пространство, прокси с белым списком.
- **Почта.** `office_mailbox_connections` (`provider yandex360 | vk_workspace | mailru | google`, `address`, `owner user | project`, `credential_id`, `project_rules`, `cursor`, `state`), писатель `channels`; операции `connect_mailbox`, `bind_mailbox_folder` (A19).
- **Источники.** `ticket:<ABC-12>` только своя задача; внешний тикет зарезервирован как `tracker:<system>:<key>`, в первом выпуске не принимается; трекер получает только принятое и отдаёт статус отметкой. Письмо `letter:<ключ из Message-ID>`. Источники в Git не идут.
- **Роли.** 12 ролей участия (`project_manager`, `business_analyst`, `system_analyst`, `architect`, `developer`, `tester`, `team_lead`, `tech_lead`, `pmo_head`, `observer`, `customer_representative`, `customer_signatory`); `system_admin` убирается, администратор системы только `users.is_admin`. Тимлид и технический лид входят в код в срезе B (таск 08): пресейл-маршрут задания (таск 13) их требует. Участие в `office_memberships` с ключом `(project_id, user_id, role)`.
- **Первый выпуск.** Срезы A-G (A16); H после. Безголовая сверка Playwright в джейле в E, руководство в E, ролик в G, интерактивный браузер в H. Дополнение 2026-10-23, A38: браузер платформы для людей в E (таски 77, 78), в H только трансляция запуска агента режимом `watch`.

### Что меняется в построенных тасках 01-03

- **Таск 01, `OfficeStore`.** `office_document_versions` становится индексом над Git: колонки по `architecture/03`, §2.5 и §2.6 (`content_sha`, `blob_sha`, `commit_sha`, `merge_request_id`, `origin`, `run_id`, `accepted_at`, `accepted_by`); статусы `draft, internal, customer, accepted, returned, signed`, `draft` и `accepted` не меняются. `office_documents` получает `family`, `editable`, `title`, `repo_path`. `office_members` заменяется `office_memberships` (миграция 0003, старая таблица только для чтения один выпуск). Миграции нумерованные со среза B (`office_schema_version`), до этого `CREATE TABLE IF NOT EXISTS` и точечные `ALTER`.
- **Публичный хук хранилища (таск 06).** `OfficeStore` выставляет публичную транзакцию (`transaction()` с соединением на поток), `knowledge` перестаёт звать приватные `_connection()` и `_lock` (долг таска 03). С `core` (таск 07) это хук транзакции `core`.
- **Таск 03, `knowledge.ingest`.** Поведение сохраняется: явное «сохранить» (текст или файл) даёт новую версию, повтор текста последней версии `created=False`. Со среза B у `editable` вида `brief` это прямая запись в `main` через `DocRepo`. Абзацы получают `kind` (`p`, `row`, `item`; строки таблиц и пункты списков отдельными единицами, изменение `split` в срезе B, миграция 0008) и `lineage`.
- **Таск 02, `project`.** Запрет смены типа читает не версии `spec` через `OfficeStore`, а `knowledge.has_version(store, project_id, family="spec", status="accepted") -> bool`. Умолчания паспорта под `office_memberships` правятся в срезе B. Код таска 02 сохраняется как есть и коммитится отдельным коммитом после прогона тестов.

### Задание для таска 04

- Модель зовётся только `routing.call` (таск 05), не `agents` напрямую и не SDK; маршрут по умолчанию «черновик текста: быстрая модель, низкое усилие» лежит в `routing`. В тестах шлюз модели (`ModelGateway`) подменяется записанным ответом. Это заменяет абзац тикета 04 «теми же учётными данными, что чат».
- Проверку «есть принятая версия задания» выставляет `knowledge.has_version`; таск 04 переводит на неё `project/_type.py` (вместо `SPEC_ACCEPTED` через `OfficeStore`).
- Таблица требований `cycle` остаётся минимальной (ключ, формулировка, версия задания, абзац брифа, статус); в срезе C её переносит миграция 0010 в `office_requirements` и `office_requirement_versions`.
- Пишет версию через `knowledge.ingest` (единственный писатель версий); статусы и переходы версии задания у `cycle`.

## Дополнения 2026-10-23

Разделы архитектуры 09-12 и сверка суперархитектора `architecture/05-sverka-superarhitektora.md` §6 (обязательна вместе с §3). При расхождении этого файла с 05 §3 и §6 верны они. Подробно: `architecture/09-planirovanie-i-upravlenie.md`, `10-postavka-testy-dokumentaciya.md`, `11-kalendar-svyaz-uvedomleniya.md`, `12-modeli-analitika-interfeis.md`; решения ADR-34-ADR-57 в `architecture/08-reshenia-adr.md`.

**Границы модулей.** Новых модулей нет. Одно новое ребро вниз: `insight → cycle` только для `trigger_risk`, `observe_risk` (09 §5.3, ADR-38). Любой модуль может слушать любое событие каталога; вызовы только вниз.

| Модуль | Новые таблицы (писатель) | Новые операции | Где |
|---|---|---|---|
| `tenancy` | `office_model_providers`, `office_model_prices`, `office_subscription_bindings`, `office_work_calendars` (D06); `office_company_users.tz`, `work_hours` | `set_model_access`, `bind_model_subscription`, `put_model_provider`, `set_provider_state`, `put_model_price`, `set_user_hours` | 12 §1-3; 09 Р-13 |
| `routing` | `office_route_outcomes`, `office_route_scores` | `resolve` с автовыбором, `record_outcome`, `run_regression` | 12 §3 |
| `knowledge` | дерево `page:*`; источники `code:<путь>`; `office_cross_links` (D01) | `transcribe`, `create_page`, `move_page`, `export(version, format, profile?)` | 09 §2.1, §9; 12 §5-6; 10 §15 |
| `bridge` | `office_bridge_field_maps`, `office_bridge_user_maps` | `map_task`, `pull_status` | 11 §7 |
| `cycle` | `office_task_history`, `office_task_batches`, `office_change_requests`, `office_saved_views`, `office_boards` | `confirm_task_batch`, `run_view`, `trigger_risk`, `observe_risk`, `choose_risk_response`, `assess_change_request`, `report_defect`, `doc_staleness` | 09 §1-5; 10 §5, §8 |
| `plan` (срез F) | `office_estimation_rounds`, `office_rate_cards`, `office_cost_entries`, `office_wbs_task_links`; Гант и освоенный объём после D06 | `open_estimation_round`, `set_rates`, `add_cost_entry`, `change_cost_preview` | 09 §6-7 |
| `delivery` | `office_check_findings`, `office_demo_renders` | `guide_inputs` (вместо `render_guide`), `final_readiness`, `register_mockup`, `confirm_mockup_choice`, `render_demo`, `index_code` | 10 §16; 12 §5 |
| `channels` | `office_meetings` (новая схема), `office_meeting_overrides`, `office_meeting_attendees`, `office_calendar_prefs`, `office_call_participants`, `office_call_tracks`, `office_channel_bindings`, `office_subscriptions` | `schedule_meeting`, `calendar_window`, `find_slots`, `meeting_context`, `bind_speaker`, `complete_binding`, `subscribe` | 11 §2-6; 09 §2.4 |
| `insight` | поля `office_metric_snapshots.dims`, `office_dashboards.spec` | `recalc_metric`; `compile_query` (D03) | 12 §4 |
| `agents` | `office_day_plans`, `office_day_plan_items`, `office_wizard_runs` | `build_day_plan`, `start_wizard`, `confirm_wizard_step` | 09 §8; 10 §12 |

**Швы.** `Embedder`, `SpeechRecognizer`, `MediaEncoder`, `BlobStore` у `knowledge`; `BrowserRunner`, `MockupEngine`, `Synthesizer` у `delivery`; `ChannelSender` у `channels`; `ModelGateway` с адаптерами формата у `routing` (00 §4.1, 05 §6.3).

**Решения, меняющие построенное или задание тасков.**

| Решение | Где |
|---|---|
| План дня один: у `agents`, не `channels.today` | 05 §6 С1; ADR-40 |
| Пояс и рабочие часы в `office_company_users` | 05 §6 С2 |
| `office_calls.meeting_id`, `occurrence_at`; у встречи нет `call_id` | 11 §2.2; ADR-46 |
| Сверку исполняет раннер без модели | 10 Р10-01; ADR-41 |
| `kind` задачи плюс `bug`; `origin` плюс `change`, `import` | 05 §6 С19 |
| `POST /tasks/slice` отвечает 200 с `blocked[]` | 05 §6 С36 |
| Отложенные пути не регистрируются; флаги возможностей в `GET /me` | 05 §6 С22 |

## Дополнения 2026-10-23, вечер

Разделы архитектуры 13-15 (A25-A37) и сверка суперархитектора `architecture/05-sverka-superarhitektora.md` §7 (обязательна вместе с §3 и §6). При расхождении этого файла с 05 §3, §6 и §7 верны они. Подробно: `architecture/13-assistent-import-otchety.md`, `14-graf-trassirovka-obratnaya-aktualizaciya.md`, `15-plan-dnya-i-rabochee-mesto.md`; решения ADR-58-ADR-69 в `architecture/08-reshenia-adr.md`; инварианты И-37-И-47 в 03 §7.

**Границы модулей.** Новых модулей нет. Рёбра чтения `insight → cycle` и `insight → knowledge` (проекции графа и хронологии, наборы отчётов; 00 §3.3); запись вниз у `insight` по-прежнему только `trigger_risk`, `observe_risk`. Входящие сообщения мессенджеров идут одним событием `channel_message.received` с `kind enum(assistant, capture, group)` (пишет `channels`, слушает `agents`).

| Модуль | Новые таблицы (писатель) | Новые операции | Где |
|---|---|---|---|
| `tenancy` | `office_role_permissions`, `office_api_tokens` (`client enum(mcp, extension)`), `office_ui_layouts`; виды лимитов `share_assistant`, `chain_guard`, `speech_minutes`, `personal_planning`; `settings.assistant_channels`, `permissions_revision` | `set_role_permissions`, `can(actor, section, action, scope)` (порядок 13 §4.7: `is_admin`, закреплённая клетка, клетка ревизии, операция домена, профиль видимости), `get_layout`, `save_layout`, `reset_layout`, `set_layout_default`, `issue_api_token(client)` | 13 §4.7; 15 §2.2 |
| `knowledge` | `office_uploads`; семейство `web:<хэш адреса>`; виды `spec:chtz-*`, `spec:ftt`, `guide:admin`, `guide:role-*`; шов `ExportRenderer` | `start_upload`, `append_upload`, `complete_upload`, `attach_upload`, `preview(source)`; `export` через `ExportRenderer`; `graph` остаётся графом ядра | 13 §2, §3.1, §4.5; 14 §2.1 |
| `bridge` | `office_bridge_links.external_status`, `external_status_at`; адаптер `google_drive` (`scope=user`) | `pull_status` пишет внешний статус и `tracker_ticket.status_changed` | 13 §2.4; 14 §4.2 |
| `project` | `settings.chain_guard`, `settings.guides_layout` | | 14 §2.3, §6.6 |
| `cycle` | `office_trace_link_history`, `office_chain_gaps`, `office_chain_gap_items`; поля `office_trace_links` (`method`, `confidence`, `requirement_version_n`, `target_version_ref`, `anchor_role`, `gap_id`), `office_requirement_versions` (`cause_kind`, `task_id`, `change_request_id`, `gap_id`), `office_requirements.audiences`, `office_tasks` (`origin=request`, `origin_evidence_id`, `ui_impact`), `office_task_history.field` (`req_keys`, `external_status`) | `requirement_history`, `trace_link_detail`, `check_chain`, `attach_gap_proposal`, `decide_chain_gap`, `dismiss_chain_gap`, `close_chain_gap` (только система), `chain_health`; проверка `gate` на `awaiting_approval → handed` (409 `chain_gap_open`) | 14 §3.4, §4, §6 |
| `delivery` | поля `office_code_commits` (`link_method`, `link_confidence`, `authored_at`, `author_external`, `files`, `mr_id`), `office_code_mrs` (`title`, ветки, `merged_at`, `task_keys`) | `suggest_commit_links`, `mark_out_of_scope`, `record_commit` с `link_method`, `guide_inputs(audience)`; события `mockup.version_added`, `commit.unlinked` | 14 §5.2, §5.3 |
| `channels` | `office_channel_inbox`; `office_channel_bindings.capture_dm`, `capture_consent_at`, `capture_consent_text_version`; `office_mailbox_connections.owner` плюс `company`, `purpose`; `office_meetings.kind` плюс `focus`, `origin`, `plan_item_id` | `send_reply(thread, message)`, `capture_inbox_item`, `set_capture`, `schedule_meeting(kind=focus)`, `connect_mailbox(owner=company, purpose=assistant)`; `ChannelSender` плюс `edit` | 13 §1.7, §1.8; 15 §1.4, §1.7 |
| `insight` | `office_reports`, `office_report_revisions`, `office_report_grants`, `office_report_exports`; `office_timeline_items` (проекция, перестраивается) | `artifact_graph`, `edge_detail`, `change_timeline`, `back_trace`, `rebuild_timeline`; `report_datasets`, `dataset_query`, `compile_report`, `render_report`, `save_report`, `set_report_grants`, `refresh_report`, `export_report`; `compile_query` (строится в G для отчётов) | 13 §4; 14 §3.5, §5 |
| `agents` | `office_assistant_threads`, `office_assistant_messages`, `office_assistant_actions`; `office_day_plan_candidates`, `office_day_plan_prefs`; поля `office_day_plans`, `office_day_plan_items`; `office_agent_runs.trigger` плюс `chat`; `office_agent_run_log.kind` плюс `action_proposed` | `AssistantRunner` (`assistant_turn`, `propose_action`, `confirm_action`, `reject_action`), `build_report`, `plan_gap_runs` (скил `chain_keeper`), `extract_plan_candidates`, `move_plan_item`, `add_plan_item`, `accept_day_plan`, `close_day_plan`, `reconcile_day_plan`, `block_in_calendar`, `unblock_in_calendar`, `decide_plan_proposal`, `build_day_plan(phase)` | 13 §1, §4.2; 14 §6.4; 15 §1 |
| `ui` | Таблиц нет; реестр виджетов это код | Каркас на dockview, дерево проекта, палитра, мобильная стопка; подписка WS `{"subscribe": {"me": true}}` и `day_plan_of`; эфемерные кадры потока токенов владельцу | 15 §2; 03 §5.9 |

**Швы.** Плюс `ExportRenderer` у `knowledge` (`html_to_pdf`, `docx_from`, `xlsx_from`, `chart_static`; Chromium своим вызовом в процессе заданий под bwrap, не через `BrowserRunner`; подделка файлами-заглушками). `ChannelSender` плюс `edit`. Шов приёмки прежний: публичные операции `cycle`; отдельные тесты допустимы для `ExportRenderer`, `tenancy.can` (порядок проверки и закреплённые клетки), `agents.move_plan_item` (сдвиг соседей, закреплённые, нет петли «пункт двигает встречу, встреча пункт»), маскировки чужого плана, согласия пересылки боту.

**Решения, меняющие построенное или задание тасков.**

| Решение | Где |
|---|---|
| `web/src/routes/OfficePage.tsx` заменяется каркасом рабочего места на dockview (таск 65, срез C); вкладки паспорта, брифа и задания становятся вкладками центра без переписывания; `ResizeHandle.tsx` и `usePanelWidth.ts` в офисе не используются | 15 §2.1, §2.9; ADR-68 |
| Панель «Спросить по проекту» (04 §7) становится вкладкой ассистента: в C на `knowledge.ask` (таск 19), в E ассистент как агент (таск 70) | 13 §1.1; 05 §7 С71, С92; ADR-69 |
| Загрузки офиса идут через `/api/office/uploads` с пределом 50 МБ для документов и 4 ГБ для медиа; `routes_files.py` и `MAX_UPLOAD_BYTES` 25 МБ файлового менеджера не меняются | 13 §2.5 |
| `src/bot`: личный диалог учётки с привязкой офиса уходит в `channels.on_update` к ассистенту; проверка привязки раньше обработчиков чата Claude Code, учётка только офиса в них не попадает даже при совпадении с `ALLOWED_USER_IDS` (обязательный тест); темы форум-группы остаются чатом Claude Code | 13 §1.7; 15 §1.1 |
| Токены MCP получают таблицу `office_api_tokens` и поле `client`; клиент `extension` только с областью «ассистент» | 13 §3.2, §7; 02 §7 |
| `knowledge.graph` остаётся графом ядра; экран «Граф» переходит на `insight.artifact_graph`, путь `GET /projects/{pid}/graph` синоним режима `neighborhood` один выпуск | 14 §3.7; 05 §7 С67 |
| Статусы задач и проверка `→ handed` получают условие `gate` (409 `chain_gap_open`) рядом с И-19 | 14 §6.11; И-43 |
| План дня таска 62 расширяется фазами, кандидатами и перетаскиванием (таск 73); модель плана одна | 15 §1; ADR-67 |
| `GET /me` отдаёт флаги возможностей и по 13-15: расширение, отчёты, серверный браузер, внешние календари (05 §6 С22) | 15 §2.10 |
| React 18.3.1 остаётся; dockview, FullCalendar 6 (стандартные модули), dnd-kit, TanStack Table, pdf.js, vl-convert, d3-scale и d3-zoom добавляются с фиксированными версиями и лицензиями при первом использовании | 15 §2.7; 13 §4.4; 14 §5.6 |

## Дополнения 2026-10-23, A38-A41, A46

Переработка браузера по A38, A39, A40, A41, A46 (бриф, записи 2026-10-23 после сверки 05 §7): `architecture/13-assistent-import-otchety.md` §3, `15-plan-dnya-i-rabochee-mesto.md` §2, сверка `architecture/05-sverka-superarhitektora.md` §8 (обязательна вместе с §3, §6, §7), ADR-70 и ADR-71 в `architecture/08-reshenia-adr.md` (ADR-60 пересмотрен). При расхождении этого файла с 05 §3, §6, §7 и §8 верны они.

**Границы модулей.** Новых модулей нет. Политика браузера у `tenancy`, сессии у `agents`, сопоставление у `insight`; граф 00 §3.3 не меняется. Один движок Chromium (образ Playwright), два хоста: `BrowserRunner` (`delivery`) в джейле запуска агента только на стенд (P23 в оставшейся части), `BrowserHost` (`agents`) на узле браузера для людей по белому списку.

| Модуль | Новые таблицы (писатель) | Новые операции | Где |
|---|---|---|---|
| `tenancy` | `office_browser_allowlist` (`scope`, `pattern`, `effect allow, deny, no_context`, `source system, connection, admin`, `private_ok`); `office_browser_extensions` (`extension_id`, `version`, `crx_sha256`, `source`, `permissions`, `host_permissions`, `state pending, approved, blocked, retired`, `enabled_for`, `targets`); `office_limits` вид `browser_sessions`; `office_companies.settings.browser`; `office_company_users.settings.browser`; клетки `browser/use`, `external`, `login_as`, `extensions`, `record_demo`, `assistant/page_context` | `browser_policy(user, url) -> allow, deny, no_context`, `set_browser_allowlist`, `request_browser_allowlist`, `approve_browser_extension`, `block_browser_extension`, `set_browser_settings` | 13 §3.4, §3.5, §3.10 |
| `agents` | `office_browser_sessions`, `office_browser_tabs`, `office_browser_events`; `office_assistant_threads.origin_channel` плюс `browser`; `office_assistant_messages` плюс `matches`, `client`; `office_assistant_actions.op` плюс `browser_action` (резерв) | `open_browser_session`, `hibernate_browser_session`, `restore_browser_session`, `close_browser_session`, `open_browser_tab`, `close_browser_tab`, `navigate_browser_tab`, `browser_page_context(tab, mode)`, `browser_login_as(tab, role)`, `record_browser_demo(session, call_id)`; шов `BrowserHost` | 13 §3.3, §3.6-3.8, §3.10 |
| `agents` (A46) | `office_import_scenarios`, `office_import_scenario_runs` | `record_import_scenario`, `describe_import_scenario` (одношаговый `routing.call` класса `browser_check`), `verify_import_scenario`, `run_import_scenario` (раннер формата 10 §2 без модели над `BrowserHost` сессии человека), `repair_scenario_locator`, `enable_import_scenario`, `disable_import_scenario` | 13 §3.12 |
| `bridge` (A46) | нет | адаптер вида `mcp_client` (`describe, check, pull` через инструменты чтения внешнего MCP-сервера, bwrap с сетью к хосту); лестница ступеней 13 §2.7 | 13 §2.7 |
| `insight` | нет | `match_artifacts(page_context, actor) -> [{node_ref, kind, confidence, edge_candidate}]` по адресу (`office_bridge_links`, репозитории и MR `delivery`, документы и источники, стенд и карта экранов), ключам `ABC-12`, `ABC-R-12` и `knowledge.search`; без модели | 13 §3.7 |
| `knowledge` | источник `web:<хэш адреса>` от клиентов `platform` и `extension`; `demo:browser-<session>` для записи демо человека | `ingest_source` прежний | 13 §3.7, §3.8; 01 §2.2 |
| `ui` | таблиц нет | Адресная строка центра; вкладка `browser` (кадры и ввод по WS `{"subscribe": {"browser_tab": id}}`), панель «На этой странице»; схема раскладки плюс `address_bar`; клиент расширения на тех же компонентах (`Chat.tsx`, карточки, мини-граф) | 15 §2.1, §2.2, §2.5; 13 §3.9 |

**Швы.** Плюс `BrowserHost` у `agents`: `open_session(user, policy)`, `open_tab(session, url)`, `navigate(tab, url)`, `input(tab, event)`, `screencast(tab) -> кадры`, `page_context(tab, mode)`, `aria_snapshot(tab)`, `screenshot(tab)`, `set_file_inputs(tab, upload_ids)`, `on_download -> upload_id`, `hibernate(session)`, `restore(session)`, `close(session)`; вариант «один сервер» это юнит `ai-workspace-office-browser` на той же машине, «рост» отдельный узел с тем же контрактом HTTP и WS; подделка записанными кадрами и снимками дерева доступности; тесты политики сети (белый список, частные диапазоны, перепривязка DNS) без Chromium. Шов приёмки прежний: публичные операции `cycle`; отдельные тесты допустимы для `tenancy.browser_policy`, `insight.match_artifacts` (адрес, ключи, поиск), шифрования и удаления профиля, регресса инъекций со страницы (02 §10).

**Решения, меняющие построенное или задание тасков.**

| Решение | Где |
|---|---|
| Вкладка `browser` каркаса (таск 65) становится живой в E: адресная строка центра одна для всех видов, `ref` вкладки это `office_browser_tabs.tab_id`; поле `address_bar` в схеме раскладки | 15 §2.1, §2.2, §2.5; 05 §8 С111 |
| Новые таски 77 (узел браузера, сессии, трансляция, белый список, стенд, запись демо) и 78 (протокол «страница → ассистент → артефакты», `match_artifacts`, панель «На этой странице») в E; 79 (каталог расширений магазина в браузере платформы) в G | 13 §3.11; 05 §8 С121; `plan.md` |
| Таск 76 перестроен: расширение «Ассистент офиса» это второй клиент протокола таска 78 (один API, два клиента), сборки для Chrome и семейства и Firefox, режимы `match` и `full`, импорт страниц, Google Drive; серверная часть расширения не дублируется | 13 §3.9; A40 |
| Таск 47 (H): трансляция запуска агента режимом `watch` той же вкладки `browser` и того же клиента трансляции; H1 и H3 больше не в H | 10 §13; 13 §3.8 |
| Третий юнит `ai-workspace-office-worker` получает соседа `ai-workspace-office-browser` со среза E; `update.sh --check-browser`; каталоги `office/browser-profiles/`, `office/browser-extensions/` | 00 §5; 12 §8.3 |
| `office_companies.settings` «запрещённые адреса расширения» (таск 76 прежней редакции) заменены строками `no_context` в `office_browser_allowlist` (таск 77) | 13 §3.4; 05 §8 С117 |
| `GET /me` плюс флаги `browser`, `browser_extensions`, `extension_modes[]`, `import_scenarios` (таск 07, таск 65) | 05 §8 С122 |
| Новый таск 80 (G): вкладка автоматизации, сценарии импорта Playwright с расписанием, адаптер `mcp_client`; исполнитель шагов формата 10 §2 выделяется из раннера таска 34 в общий модуль, чтобы `delivery` (джейл запуска) и `agents` (сессия человека) исполняли один формат | 13 §2.7, §3.12; ADR-72 |
| Принципы 15 (контекст собирается онлайн, A39) и 16 (ни одна задача не требует выхода, A41) в 00 §2 проверяются при приёмке каждого среза по картам 05 §8.3 и §8.4 | 00 §2; ADR-71 |

## Дополнение 2026-10-24: коннекторы и библиотека MCP (A47, A48)

- `bridge`: у подключения поля `mode` (`link`, `index`, `live`) и `scope`; адаптеры систем в `src/office/bridge/adapters/<система>/`; способ адаптера `native` или `mcp`. Режим `live` в ядро не пишет.
- `agents`: новая таблица `office_mcp_servers` (id, название, транспорт, адрес или команда из записи, закреплённая версия, имена секретов, `tool_allowlist`, режим `read` или `write`, уровень доверия, область, статус). Единственный писатель: `agents`. Вызов только через `routing` и файрвол инструментов.
- `tenancy`: вид учётных данных `oauth_token` рядом с `connector_secret`.
- Подробности: `architecture/19-konnektory-i-biblioteka-mcp.md`. Таски 81-84 среза G. Код пока не пишется: разработка остановлена пользователем 2026-10-22.

## Дополнение 2026-10-26 (сверка 24): артефакты PM Book, версии, актуализация, Гант, сессии проработки (A53-A64)

Источник: `architecture/21`, `22`, `23` после сверки `architecture/24-sverka-superarhitektora-pmbok.md`; при расхождении верен 24. Модулей не прибавилось, направление зависимостей прежнее. Имена из `spec.md` «Дополнения 2026-10-26», заменённые сверкой: `office_brief_questions` → `office_elicitation_turns`; `office_schedule_settings` → `office_gantt_settings`; вид `report:final` → `final_report`; события `brief_question.*` → `elicitation.*`; `cycle.check_vision` → `agents.check_vision` плюс `cycle.record_vision_check`.

| Модуль | Новые таблицы (единственный писатель) | Новые операции | Срез |
|---|---|---|---|
| `knowledge` | `office_artifact_templates`, `office_artifact_presets`, `office_artifact_inputs`, `office_artifact_input_heads`, `office_doc_sets` | `note_input_head(project, input_kind, input_ref, latest, latest_accepted?)` (зовут `cycle`, `plan`), `record_inputs(version_id, inputs[])`, `sync_state(project)`, `create_doc_set(project, reason)` | B |
| `cycle` | `office_brief_submissions`, `office_vision_checks`, `office_stakeholders`, `office_assumptions`, `office_issues`, `office_lessons`, `office_vendors`, `office_register_history`, `office_actualizations`; поле `office_decisions.typical` | `draft_artifact(project_id, template_id, inputs)` (`draft_spec` её частный случай, имя сохраняется), `accept_brief_submission`, `snapshot_register(project, kind)`, `check_gate(project, phase)`, `record_vision_check(version_id, items[])`, `actualize(project, doc, version)` | B, C (`office_vendors` G) |
| `plan` | `office_gantt_settings`, `office_gantt_ops` | `draft_wbs(project_id, spec_version_id)`, `propose_links(project_id)`, `gantt_preview(project, ops[])`, `gantt_apply(project, ops[], calc_epoch)` | F |
| `insight` | нет | `similar_projects(project_id)` (агрегаты по паспорту, порог) | G |
| `agents` | `office_elicitation_sessions`, `office_elicitation_turns`; `office_solutions.kind` плюс `project_case` | `start_elicitation`, `answer_elicitation`, `synthesize_elicitation`, `check_vision(version_id)`; слушает `artifact.outdated` (обновление зависимых по `10` §8.1) и `register.row_changed` (карточка опыта из урока) | B (сессии), G (опыт) |

- Виды документов в Git: `plan:*`, `final_report`, `final_report:*`, `gate:*`, `act:phase-*` (в `act:*`), `register:*`, `status_report`, `status_report:*`, `elicitation:*`.
- Класс операций моделей `elicitation` (сильная модель, среднее усилие); `brief_interview` в `draft_text`.
- Клетки матрицы: `templates/manage`, `artifacts/create`, `registers/view`, `registers/edit`, `gantt/edit`, `elicitation/run`, `elicitation/customer`, `library/propose`, `library/approve`.
- События: `template.published`, `artifact.drafted`, `brief.submitted`, `brief.accepted`, `register.row_created`, `register.row_changed`, `register.snapshot_created`, `actualization.started`, `actualization.step_done`, `actualization.completed`, `actualization.failed`, `artifact.outdated`, `doc_set.created`, `gantt.changed`, `gantt.deadline_unreachable`, `elicitation.session_started`, `elicitation.question_asked`, `elicitation.answered`, `elicitation.session_done`, `vision_check.finished`.
- Ошибки: 409 `input_cycle`, 409 `vision_contradicted`.
- Инварианты И-61-И-74: `architecture/03` §7, дополнение сверки 24.
- Код пока не пишется: разработка остановлена пользователем 2026-10-22.

## Дополнение 2026-10-26 (сверка 27): уведомления, ручное ревью, отчёты и презентации, права и утечки (A65-A72)

Источник: `architecture/25`, `26` после сверки `architecture/27-sverka-superarhitektora-prava-i-utechki.md`; при расхождении верен 27. Модулей не прибавилось (15), направление зависимостей прежнее: повторная проверка классов результата при публикации и экспорте идёт через `tenancy`, а не через `insight`.

| Модуль | Новые таблицы (единственный писатель) | Новые операции | Срез |
|---|---|---|---|
| `tenancy` | `office_customer_org_units`; поле `office_model_prices.tier` | `audience_scope(actor, scope, audience, kind)` (для всех запусков агентов, не только результатов), `import_customer_org_units`; `scope` отдаёт маску классов и метки области | E, G3 |
| `knowledge` | поля `office_fragments.data_classes`, `scope_tags`, `office_document_versions.data_classes`, `office_artifact_templates.audience`, `review_policy`, `review_owner_role`, `review_sla_days`, `deliverable`; семейства `research`, `support_ticket` | `search(..., audience)` только в одном проекте; `import_agent_commits` проверяет источник цитат по аудитории вида; `describe_for_notification`, `visible_to` | C, C2, G3 |
| `cycle` | `office_artifact_reviews`, `office_review_items`, `office_review_requests`, `office_review_assignments`, `office_deliverable_checks`, `office_support_tickets`, `office_support_ticket_events`, `office_support_sla_policies`, `office_system_modules`; поля `office_comments.review_request_id`, `review_item_id` | `open_artifact_review`, `decide_review_item`, `complete_artifact_review`, `reject_artifact_review`, `delegate_review`, `create_review_request`, `respond_review_request`, `remind_review_request`, `cancel_review_request`, `review_request_summary`, `record_research_result`, `record_deliverable_check`, `upsert_support_tickets`, `support_sla_state`, `set_system_modules` | C2, G3 |
| `channels` | `office_notification_user_settings`, `office_notification_policies`, `office_reminders`; правки `office_notifications`, `office_notification_prefs`, `office_project_chats.kind` плюс `management` | `resolve_recipients`, `deliver`, `may_deliver`, `render`, `set_prefs`, `set_user_settings`, `set_policy`, `snooze`, `mute_project`, `create_reminder` | F (F2 предложен) |
| `insight` | `office_fact_packs`, `office_adoption_daily`, `office_adoption_sources` | `collect_facts`, `verify_deliverable` (зовёт только `agents`), `render_deliverable`, `ingest_adoption` | G3 |
| `agents` | `office_context_packs`, `office_research_runs`, `office_research_answers`, `office_deliverable_runs`, `office_prompt_overlays`, `office_deliverable_subscriptions`; `office_solutions.kind` плюс `product_card`, поля `external_use`, `consent_ref` | `build_context_pack`, `estimate_research`, `start_recheck`, `start_council`, `confirm_research`, `cancel_research`, `decide_research`, `apply_research`, `prepare_deliverable`, `activate_overlay`, `set_deliverable_subscription` | E (E2 предложен), G3 |
| `routing` | нет | `resolve(..., hints {min_tier?, exclude?})` не обходит `export_ban` | E |
| `plan` | поле `office_gantt_settings.editors` | нет | F |
| `delivery` | значение `office_ops_environments.kind` плюс `demo_stand` (таблица у `ops`) | `screen_assets(project, filter, audience)`, `capture_screens` | G3 |
| `bridge` | класс адаптера `service_desk` | `pull`, `describe`, `check`; вызовы `live` и внешних MCP в границах пространства проекта | G3 |

- Классы данных (один реестр, `architecture/03` §2.5): `team`, `customer`, `budget`, `internal_text`, `code`, `usage`, `personal`, `showcase`, `management_chat`. Имена `management` (вид чата, аудитория результата) и `customer.internal` (раздел матрицы) классами не являются.
- Аудитории: `internal`, `management`, `customer`, `prospect`.
- Классы моделей: `senior_check`, `council_member`, `council_arbiter`; доли `share_council`, `share_deliverables`.
- Виды документов в Git: `stage_report:*`, `support_report:*`, `load_report:*`, `adoption_report:*` (плюс прежние `presentation:*`, `status_report:*`); вне Git: `research:<id>`, `support_ticket:<id>`.
- Клетки матрицы (одна таблица `architecture/13` §4.7, дополнение 27): разделы `notifications`, `review`, `deliverables`, `support` (с `view_texts`), `adoption`, `showcase`, `chats/view_management`.
- События: `architecture/03` §6, дополнение сверки 27; `member.removed` только при снятии последней роли, иначе `member.role_changed`.
- Ошибки: 409 `review_incomplete`, `stale_head`, `items_pending`, `agent_touched_accepted`, `estimate_changed`, `audience_not_allowed`, `not_approved`, `review_required`; 422 `reason_required`, `reviewer_cannot_see`, `mode_not_allowed`, `single_model_only`, `hard_check`, `lint_unconfirmed`, `auto_release_not_allowed`, `role_not_permitted`, `threshold_above_cap`, `above_company_cap`, `kind_locked`; импорт коммита агента отказывает с `source_outside_audience`.
- Номера тасков: 102-106 (`25`), 107-109 (чаты `18`, были 86-88), 110-119 (`26`), 120-124 (`ops` `17`, были 81-85).
- Инварианты И-75-И-105: `architecture/03` §7, дополнение сверки 27.
- Код пока не пишется: разработка остановлена пользователем 2026-10-22.

## Дополнение 2026-10-27 (проверка ИБ 29): права, сессии, ключи, журналы (A75)

- Операции: `tenancy.set_privacy_officer(actor, user, confirm_by)`; `tenancy.set_company_role_flag(actor, user, flag enum(pmo_head, observer_unit, observer_company))`; `tenancy.revoke_sessions(user, reason)` и серверная эпоха сессии; хранитель ключей за швом `KeyVault`: `wrap`, `unwrap`, `sign`, `verify` по сокету с проверкой вызывающего; `knowledge.reclassify(project, kind | source)`; `knowledge.import_agent_bundle(run, bundle)` вместо разбора клона; `core.anchor_audit()`; санитайзер вывода одной функцией фронта и `ExportRenderer`.
- Поля: `office_fragments.origin enum(human, connector, agent, external_client, model_generated)`; `office_events.data_classes`; `office_api_tokens.expires_at` обязателен; `office_egress_rules.purpose` плюс `browser`, `stand`, `package_mirror`; `office_documents.data_classes` с открытия ветки.
- Ошибки: 409 `same_person`, `org_mismatch`, `cloud_not_confirmed`; 422 `secret_not_allowed`; 404 вместо 403 на скрытую цель у изменяющих методов.
- События и виды уведомлений: `audit.chain_broken`, `privacy.egress_rule_changed` (неотключаемый), `access.admin_as_role` (сразу, неотключаемый).
- Клетки: строка `privacy_officer`; `terminal/use`; `pii/*`, `sovereignty/*` закреплены.
- Токены клиентов `mcp`, `extension` действуют только на своих маршрутах (И-124).
- Таски 138-143; инварианты И-122..И-139 (`architecture/03` §7, дополнение проверки ИБ 29; `architecture/29` §10).

## Дополнение 2026-10-27 (сверка 32): проектный офис, портфель, политика ИИ, дополнения PMBOK 8 (A76-A83)

Источник: `architecture/31-proektnyj-ofis-portfel-ii-politika.md` после сверки `architecture/32-sverka-superarhitektora-pmo-pmbok.md`; при расхождении верен 32. Модулей не прибавилось (15), направление зависимостей прежнее: вехи ворот `cycle` получает вызовом сверху, черновик итога зрелости создаёт `agents`, старт по решению комитета собирает `ui`.

| Модуль | Новые таблицы и поля (единственный писатель) | Новые операции | Срез |
|---|---|---|---|
| `tenancy` | `office_pmo_profiles`, `office_ai_policy_profiles`, `office_strategic_goals`; `office_work_calendars` (было D06); `office_model_providers.node_power_kw` | `propose_pmo_profile`, `preview_pmo_profile`, `activate_pmo_profile` (только из `cycle`), `pmo_profile`, `propose_ai_policy`, `activate_ai_policy` (только из `cycle`), `ai_policy`, `set_strategic_goal`, `set_work_calendar`, `import_work_calendar`; проверка политики в `propose_cloud`, `confirm_cloud` | C2, G2, F |
| `routing` | `office_model_evals.suite`, `office_model_class_gates` | `run_bias_suite`, `class_gate_state`; `resolve` с проверкой профиля политики и ворот классов | B3, C2 |
| `knowledge` | `office_document_versions.space_audience`; `office_artifact_templates.focus_area` (было `phase`), `required` у пункта набора; виды входа `pmo_profile`, `ai_policy`, `contract_stages` | `company_doc(company, kind)`, `paragraph_origins(version)`; проверка слияния пространства компании (422 `company_space_leak`) | B2, C2 |
| `project` | `office_projects.space_kind`, `office_project_goal_links`; поле настроек `preset_deviations` | `ensure_company_space`, `link_goal`, `decide_goal_link`, `approve_start(project, decision_ref)`, `record_preset_deviation` | C2, G2 |
| `cycle` | `office_gate_milestones`, `office_contribution_records`, `office_benefits`, `office_benefit_measurements`, `office_procurements`, `office_procurement_offers`; поля `office_review_items.origin_kind`, `origin_run_id` | `check_gate(project, milestone_key)` (было `check_gate(project, phase)`), `register_milestone`, `record_contribution`, `upsert_procurement`, `add_offer`, `select_vendor`, `measure_benefit`; маршрут `company_doc` | C2, E2, G |
| `plan` | нет | `funding_profile`, `role_demand`; зовёт `cycle.register_milestone` | F |
| `contracts` | `office_contract_stages` | `set_contract_stages` (зовёт `cycle.register_milestone`), `set_stage_state` | G |
| `insight` | `office_portfolio_cycles`, `office_portfolio_scores`, `office_portfolio_scenarios`, `office_portfolio_decisions`, `office_role_capacity`, `office_maturity_campaigns`, `office_maturity_answers`, `office_maturity_results`; у `office_dashboards` поле `scope_id`, значение `source = widgets`, `spec_version = 2` | `open_portfolio_cycle`, `score_project`, `rank`, `evaluate_scenario`, `suggest_scenario`, `freeze_portfolio`, `record_decision`, `mark_decision_executed`, `portfolio_widget`, `open_maturity_campaign`, `submit_maturity_answers`, `close_maturity_campaign`, `maturity_indicators` | G2 |
| `agents` | нет | слушатель `maturity_campaign.closed` (черновик `pmo:maturity`); инструмент `company_docs` | E, G2 |

- Виды документов в Git: `pmo:methodology`, `pmo:maturity`, `policy:ai_use` (пространство компании); `plan:finance`, `plan:benefits-finance`, `business_case:finance` (`budget`); `business_case`, `plan:stakeholder_engagement`, `plan:benefits`, `procurement:sow`, `procurement:rfp`, `register:benefits`, `register:procurements` (`team`); `gate:<веха>`, `act:stage-<веха>` с ключом вехи `MS-N`. В строке «Дополнение 2026-10-26 (сверка 24)» этого файла `check_gate(project, phase)` и `act:phase-*` читаются как `check_gate(project, milestone_key)` и `act:stage-*` (A79).
- Клетки матрицы (одна таблица `architecture/13` §4.7, дополнение сверки 32): разделы `pmo`, `portfolio` (дополнение), `project` (`assign_pm`, `approve_start`), `ai`, `procurement`, `calendar`.
- События: `architecture/03` §6, дополнение сверки 32; события несут ключи и ссылки, не значения.
- Ошибки: 409 `policy_forbids`, `bias_failed`, `start_decision_required`, `decision_not_found`, `decision_not_frozen`, `same_person`; 422 `company_space_leak`, `space_no_channels`, `review_floor`, `system_class`, `section_not_permitted`, `generated_section` (пункт ревью).
- Номера тасков: 144-151 (`architecture/31` §11); расширяются 13, 32, 44, 53, 64, 68, 70, 75, 89, 93, 94, 95, 96, 104, 112, 115, 119, 127, 134.
- Инварианты И-140..И-150 и дополнение И-123: `architecture/03` §7, дополнение сверки 32.
- Код пока не пишется: разработка остановлена пользователем 2026-10-22.

## Дополнение 2026-10-28 (сверка 35): категории рисков, командная оценка, S-кривая, прогнозы, рыбья кость, контрольная карта, рассеяние, карта историй (A84-A91)

Источник: `architecture/33`, `34` после сверки `architecture/35-sverka-superarhitektora-celostnost.md`; при расхождении верен 35. Модулей не прибавилось (15), рёбер вызова тоже. Запись вниз у `insight` прежняя (`trigger_risk`, `observe_risk`). Правило подписки уточнено (`00` §3.3, дополнение 35): нижний модуль слушает событие верхнего, только если событие несёт ключи, а обработчик пишет свои таблицы и не зовёт и не читает верхний модуль.

| Модуль | Новые таблицы и поля (единственный писатель) | Новые операции | Срез |
|---|---|---|---|
| `tenancy` | `office_risk_categories` (удаления нет, только архив) | `set_risk_category`, `archive_risk_category`, `risk_categories(company, project?)` | C2 |
| `cycle` | `office_risks.category_id`; `office_cause_diagrams`, `office_cause_branches`, `office_causes` | `open_cause_diagram`, `draft_causes`, `decide_cause`, `promote_cause_to_lesson`, `propose_risk_from_signal`; слушатель `process.out_of_control`, `gantt.forecast_shifted` | C2, E2, F2 |
| `plan` | `office_story_maps`, `office_story_activities`, `office_story_cards`; `office_gantt_forecasts`; `office_ev_snapshots` (только `pv`, `ev`, `ac`, `spi`, `spi_t`) | `earned_value` (часть по срокам), `forecast_schedule`, `draft_story_map`, `move_story_item`, `decide_story_item`, `snapshot_story_map` (зовёт `cycle.draft_artifact`) | F2 |
| `insight` | `office_team_surveys`, `office_team_survey_tokens`, `office_team_survey_answers`, `office_team_survey_results`; метрики `cycle_time`, `review_return_rate`, `spi_week`, `model_point_reject_rate`, набор `team_effectiveness` | `open_team_survey`, `submit_team_survey`, `close_team_survey`, `team_effectiveness`, `control_chart`, `process_portfolio`, `scatter` | E2, F2, G2 |

- Клетки матрицы (одна таблица `architecture/13` §4.7, дополнение сверки 35): `insight/view_process`, `insight/view_scatter`, `plan/view_story_map`, `plan/edit_story_map`, `team/view_effectiveness`, `team/run_survey`, `pmo/edit_risk_taxonomy`. Ключ `plan.budget` цельный, не раздел `plan` с действием `budget`.
- События (`architecture/03` §6, дополнение 35): `process.out_of_control` (`insight`), `gantt.forecast_shifted` (`plan`), `team_survey.closed` (`insight`); только ключи. `schedule.*` остаётся за расписаниями агентов. Задание `gantt_forecast`.
- Виды уведомлений К15 `risk_quality` (`architecture/25` §3.3): `process.out_of_control` (МП, РПО области; ссылка РПО вне проекта на портфельный срез), `gantt.forecast_shifted` (МП, РПО), класс «Сразу», до таска 102 только колокольчик веба.
- Виды документов в Git: `story_map:customer` (класс `customer`, публикует МП после ручного ревью).
- Ошибки: 409 `diagram_exists`, `map_exists`, база не принята; 422 `category_required`, `person_cause`, `dimension_forbidden`, `pair_forbidden`, `sample_too_small`; скрытое 404.
- Портфельный виджет W11 «S-кривые проектов» продолжает каталог `architecture/31` §5.1, строит таск 150.
- Таски 152-159: C2 152; E2 153, 156, 158; F2 154, 155, 157, 159 (`plan.md`, дополнение сверки 35).
- Инварианты И-151..И-167: `architecture/03` §7, дополнения 2026-10-28.

## Дополнение 2026-10-29 (сверка 37): двенадцать артефактов в первом выпуске (A92-A103)

Источник: `architecture/36` после сверки `architecture/37-sverka-superarhitektora-posle-36.md`; при расхождении верна 37. Модулей не прибавилось (15), рёбер вызова тоже. Гистограмму и прогноз считает `plan`, читая `tenancy` и `project` вниз по графу. Связь стенда с ИСР ставит `plan` вызовом `project` сверху вниз.

| Модуль | Новые таблицы и поля (единственный писатель) | Новые операции | Срез |
|---|---|---|---|
| `tenancy` | `office_absences` (`id`, `company_id`, `user_id`, `start_on`, `end_on`, `reason enum(vacation, business_trip, training, personal)?` класса `personal`, `created_by`); `office_api_tokens.client` плюс `screen`, поля `view_ref`, `show_assignees` | `set_absence`, `busy_intervals(viewer, project, period)` (без причины), `issue_screen_token`, `revoke_screen_token` | F2, E2 |
| `project` | `office_assigned_resources` (`id`, `project_id`, `wbs_item_id?`, `kind enum(stand, server, environment)`, `title`) | `set_assigned_resource`, `set_resource_wbs` (зовёт только `plan`) | G2 |
| `cycle` | `office_tasks.risk_score`; `office_risk_task_links` (`risk_id`, `task_id`, `created_by`) | `link_risk_task`, `unlink_risk_task`; пересчёт `risk_score` внутри `cycle` | E2 |
| `plan` | `office_wbs_items.department_id` (на `office_departments`), `office_wbs_items.estimate_basis` | `roadmap`, `network_view`, `draft_release` (зовёт `cycle.draft_artifact`), `resource_load`, `role_capacity_forecast` (на запрос, без хранения), `link_resource(wbs_item_id, resource_id)` | F2, G2 |

- Клетки матрицы (одна таблица `architecture/13` §4.7, дополнение сверки 37): `plan/view_resource_load`, `project/share_screen`, `project/view_stands`, `project/edit_stands`, `calendar/edit_absence_others`.
- Виды документов в Git: `plan:release`, `plan:test` (класс `team`, аудитория `internal`); `roadmap:customer`, `plan:release:customer`, `plan:test:customer` (класс `customer`, публикует МП после ручного ревью, правила И-167 и И-171). Виды «Дорожная карта», «Сеть», «Гистограмма», «Прогноз ролей», «Подразделения на ИСР» это экраны, не документы.
- Путь показа общего экрана: токен во фрагменте адреса, обмен на cookie пути показа; другие API на токен `screen` отвечают 401.
- События: новых нет. Выпуск и отзыв токена и изменения отсутствий пишутся в аудит без значения токена и без причины.
- Ошибки: 422 `dimension_forbidden` (прежняя), `reason_owner_only`, `secret_like_value`, `quantity_in_team_text`; скрытое и отозванное 404.
- Имя `org_unit_id` из первой редакции `36` не вводится: поле `department_id`, как в `office_ops_servers` и `office_pmo_profiles`. `office_customer_org_units` это подразделения заказчика.
- D06 после раздела 36: табель `office_worklogs`, доли участия `office_allocations`, внешняя занятость `office_busy_blocks`, CPI, EAC, ETC, VAC, TCPI. Фразы «отсутствия людей D06» в `architecture/09` §1.2, §6.5 и `architecture/31` §2.3, §4.4, §6.3, §16 читаются по `36` §8.
- Таски 160-171: E2 161, 163, 166; F2 160, 162, 165, 167, 168, 169, 170; G2 164, 171. Счёт: E2 10, F2 16 (предел), G2 7.
- Инварианты И-168..И-174: `architecture/03` §7, дополнения 2026-10-29.

## Дополнение 2026-10-30: очередь задач роли (A104)

Источник: `architecture/38-ochered-zadach-roli.md`. Модулей не прибавилось (15), рёбер вызова тоже. Строку пишет `cycle` в той же транзакции, что перевод предмета в состояние «ждёт менеджера проекта».

| Модуль | Новые таблицы и поля (единственный писатель) | Новые операции | Срез |
|---|---|---|---|
| `cycle` | `office_queue_items` (`role`, `category`, `customer_kind?`, `scope enum(project, customer_personal)`, `owner_user_id?`, `subject_type`, `subject_id`, `source`, `status enum(open, done, dismissed)`, `opened_by`, `closed_by?`, `close_reason?`) | `enqueue_queue_item`, `list_queue`, `validate_queue_item`, `export_queue_task`, `dismiss_queue_item`, `move_queue_item`, `edit_queue_cell`, `queue_cell` | G2 |

- Клетки матрицы (одна таблица `architecture/13` §4.7): `queue/view`, `queue/act`. По умолчанию обе у менеджера проекта своих проектов.
- Экран: `/office/queue` и `/office/:id/queue`, форма «Очередь задач». Шесть вкладок только у `project_manager`. Представления `team`, `table`, `calendar`, `gantt`. Контуры `project` и `customer_personal`. Сегмент `queue` статический, выше `/office/:id`.
- События: `queue.opened`, `queue.closed`, `queue.exported`. Только ключи. Вид уведомления `queue.opened` по правилам `architecture/25`.
- Ошибки: 409 `export_before_validation`, `invalid_transition`; 422 `category_unknown`, `reason_required`, `field_not_editable`, `scope_unknown`; заказчик, чужой проект и чужой владелец контура «С заказчиком» 404.
- Экспорт зовёт уже существующие доску задач и `bridge.push_accepted`. Новый трекер не заводится.
- Таск 172: G2. Счёт G2: 8. Инварианты И-175 и И-176: `architecture/03` §7, дополнение 2026-10-30. Представления очереди не пишут календарь `11` и Гант плана `09`.

## Дополнение 2026-10-30: реестр интерактивных артефактов (A105)

Источник: `architecture/39-reestr-interaktivnyh-artefaktov.md`. Модулей не прибавилось (15). Паспорт пишет `cycle`. Поиск с датой остаётся у `knowledge`. Последствия читает `insight`.

| Модуль | Новые таблицы и поля (единственный писатель) | Новые операции | Срез |
|---|---|---|---|
| `cycle` | `office_functions`, `office_function_slots`, `office_function_witnesses`, `office_function_gap_dismissals`, `office_function_actions`, `office_function_impacts` | `create_function`, `set_function_owners`, `propose_function_slot`, `confirm_function_slot`, `record_function_witness`, `dismiss_function_gap`, `open_function_action`, `function_passport` | G2 |
| `knowledge` | `office_search_log.sourced`, `office_search_log.duration_ms` | правило ответа: утверждение без ссылки и без даты не входит в ответ | G2 |
| `insight` | нет своих таблиц паспорта | `function_impact` | G2 |

- Клетки матрицы (одна таблица `architecture/13` §4.7): `ia/view`, `ia/act`. По умолчанию обе у менеджера проекта и системного аналитика своих проектов.
- Экран: `/office/:id/ia` реестр принятых видов, `/office/:id/functions/:key` паспорт. Сегодня в реестре одна строка, IA-01. Сегмент `ia` статический, выше `/office/:id`.
- События: `function.created`, `function.witnessed`, `function.action_opened`. Только ключи. Уведомлений нет.
- Ошибки: 409 `action_exists`. 422 `slot_unknown`, `reason_required`, `stand_required`, `secret_like_value`. Заказчик 404.
- Действие из неясности зовёт очередь `38`. Новый список входящих не заводится.
- Таски 173-176: G2. Счёт G2: 12. Инварианты И-177 и И-178: `architecture/03` §7, дополнение 2026-10-30. Предложения IA-02..IA-07 таблиц не имеют.
