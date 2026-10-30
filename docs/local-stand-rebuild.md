# Локальный стенд: пересборка без потери данных

Канон для разработки в git-клоне. Прод (`install.sh`, `update.sh`) сюда не входит.

## Обычная пересборка (после правок кода или фронта)

```bash
bash scripts/run_stand.sh
```

| Что | Действие |
|-----|----------|
| `data/sessions.db` | **не трогаем** (пользователи, настройки админки, `office_*`, токен Redmine в `office_redmine_account`, проекты офиса, чаты) |
| `data/sessions.artifacts.db` | не трогаем (журнал артефактов рядом с sessions) |
| Файлы в `PROJECTS_DIR` / `data/local-projects` | не удаляем, только `mkdir` при remap после явного restore |
| `web/dist` | пересборка, если `web/src` новее `web/dist` (`STAND_SKIP_WEB_BUILD=1` отключает) |
| Справочники Redmine kanban | `seed_redmine_lookups.py --if-empty` (только если строки ещё нет) |
| Процесс на :8600 | stop → `run_web.py` |

При старте веба (не только пересборка): удаляются **только** устаревшие строки `sessions` (пустые старше 24 ч или любые старше 7 суток). Сущности офиса, пользователи и настройки подключений не затрагиваются. Отдельно: retention строк `messages` для tool_use базы ФАКТ (см. `persistence.kb_tool_retention_days` в config).

`ensure_admin_user` при старте **не** перезаписывает существующего админа паролем из `.env`.

## Явный сброс SQLite из дампа (уничтожает локальные отличия от дампа)

```bash
STAND_CONFIRM_RESTORE=1 bash scripts/run_stand.sh --restore
```

или только подмена БД:

```bash
STAND_CONFIRM_RESTORE=1 bash scripts/restore_stand_db.sh --force
```

Без `STAND_CONFIRM_RESTORE=1` скрипт отказывается затирать существующую БД.

При restore из `data/dumps/`:

- рабочий файл `sessions.db` **полностью** заменяется копией дампа;
- в копии чистятся строки `messages` tool_use ФАКТ (`scrub_kb_history`, В43-3);
- пути `projects.abspath` переписываются на локальный `PROJECTS_DIR` (UPDATE, не удаление каталогов на диске);
- пароль админа в **рабочей** БД выравнивается с `.env` (`align_stand_admin`), файл дампа не меняется;
- справочники kanban сидятся **только если пусто** (`--if-empty`).

Первый запуск без файла БД: restore из дампа **без** подтверждения (ещё нечего терять).

## Свежий дамп с прода

Только по просьбе: `STAND_DUMP_FETCH=1 … fetch_stand_dump.sh`. Сам fetch **не** подменяет рабочую БД. После загрузки дампа сброс: `STAND_CONFIRM_RESTORE=1 bash scripts/run_stand.sh --restore`.

## Что не запускать «для пересборки UI»

- `bash scripts/run_stand.sh --restore` без необходимости (сброс токенов и офиса).
- `seed_redmine_demo.py` без `--project-id` (демо-задачи, не часть `run_stand`).
- `install.sh` / `update.sh` на машине разработки (другой сценарий, не локальный стенд).

См. также `data/dumps/README.md`, `CLAUDE.md` § локальный стенд.
