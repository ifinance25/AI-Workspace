# Дампы SQLite локального стенда

Канон: эта папка, `AI-Workspace/data/dumps/` в git-клоне. Vault `artifacts/` для дампов не используем.

В git не класть: `*.db`, `*.sqlite`, WAL/SHM. В файлах сессии, пользователи, ключи API.

## Сборка стенда из дампа

Из корня git-клона:

```bash
bash scripts/run_stand.sh
```

Только подмена БД (стенд на порту 8600 сначала останавливается):

```bash
bash scripts/restore_stand_db.sh
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

На сервере (если скрипт недоступен): не обязательно стопать `vels-claude`.

```bash
sudo -u vels-bot sqlite3 /opt/vels-claude/data/sessions.db ".backup '/tmp/sessions-YYYY-MM-DD.db'"
scp user@host:/tmp/sessions-YYYY-MM-DD.db data/dumps/sessions-YYYY-MM-DD.db
cd data/dumps && ln -sfn sessions-YYYY-MM-DD.db sessions.latest.db
```

Затем `bash scripts/run_stand.sh`.
