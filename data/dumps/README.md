# Дампы SQLite локального стенда

Контракт пересборки без потери данных: [docs/local-stand-rebuild.md](../docs/local-stand-rebuild.md).

Канон: эта папка, `AI-Workspace/data/dumps/` в git-клоне. Vault `artifacts/` для дампов не используем.

В git не класть: `*.db`, `*.sqlite`, WAL/SHM. В файлах сессии, пользователи, ключи API.

## Сборка стенда

Из корня git-клона:

```bash
bash scripts/run_stand.sh
```

Обычный запуск: останавливает старый процесс на :8600, при необходимости собирает фронт (`web/src` новее `web/dist`), поднимает веб. **Рабочую `data/sessions.db` не затирает** (токены Redmine, проекты офиса, демо-сиды сохраняются).

Полный сброс из дампа (первый запуск без БД или явная просьба):

```bash
bash scripts/run_stand.sh --restore
# или STAND_CONFIRM_RESTORE=1 STAND_FORCE_RESTORE=1 bash scripts/run_stand.sh
```

Только подмена БД без веба:

```bash
bash scripts/restore_stand_db.sh          # пропуск, если БД уже есть
bash scripts/restore_stand_db.sh --force   # нужен STAND_CONFIRM_RESTORE=1
```

Адрес по умолчанию: `http://127.0.0.1:8600`.

Нужен файл:

- `sessions.latest.db` (symlink или копия), или
- `sessions.db`, или
- самый новый `sessions-YYYY-MM-DD.db`

Если файла нет, скрипт выходит с ошибкой и **не** ходит на прод.

## Обновить дамп с прода (только по явной просьбе)

Скрипт сам не запускать «на всякий случай». Когда пользователь попросил свежий дамп:

```bash
STAND_DUMP_FETCH=1 STAND_DUMP_SSH=user@host bash scripts/fetch_stand_dump.sh
```

`STAND_DUMP_SSH`: `user@host` или `Host` из `~/.ssh/config`. IP в репозиторий не зашивать.

На сервере (если скрипт недоступен): не обязательно стопать `ai-workspace`.

```bash
sudo -u ai-workspace sqlite3 /opt/ai-workspace/data/sessions.db ".backup '/tmp/sessions-YYYY-MM-DD.db'"
scp user@host:/tmp/sessions-YYYY-MM-DD.db data/dumps/sessions-YYYY-MM-DD.db
cd data/dumps && ln -sfn sessions-YYYY-MM-DD.db sessions.latest.db
```

Затем `bash scripts/run_stand.sh --restore` (или `--restore-only`). Restore после копирования переписывает
`projects.abspath` (и связанные пути) на локальный `PROJECTS_DIR` и создаёт
пустые каталоги проектов. Файл дампа в `data/dumps/` не меняется.
