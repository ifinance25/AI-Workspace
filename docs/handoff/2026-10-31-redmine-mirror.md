# Зеркало Redmine: заметки от сверки 43 для агента Cursor

Дата: 2026-10-31. Автор: сессия сверки `architecture/43` (Claude). Адресат: агент Cursor,
который ведёт зеркало Redmine (`src/office/redmine_mirror/`, `scripts/restore_stand_db.sh`,
коммиты `0c6bcb9`, `280121b`, `8a4204a`). Файл можно удалить, когда оба пункта закрыты.

## Что уже исправлено за вас

- `64c737c`: в `load_project` ветка `except (RedmineUnavailableError, *_DOWN)` поставлена выше
  `except MirrorError`. `RedmineUnavailableError` наследует `MirrorError`, поэтому при недоступном
  Redmine копия не сохранялась. Два теста `tests/office/test_redmine_mirror.py` снова зелёные.
  Перед правками `_mirror.py` подтяните `develop`.

## Что осталось

1. `tests/test_restore_stand_db.py`: `test_restore_copies_dump_to_working_db` и
   `test_restore_remaps_prod_paths_and_mkdirs` падают при прогоне файла целиком и проходят
   по одному. Похоже на зависимость от порядка или общего состояния после шага
   `seed_redmine_lookups`. Причина не искалась: `scripts/restore_stand_db.sh` был с вашими
   незакоммиченными правками.
2. Коммитить только свои файлы (`git add <путь>`), без `git add -A` и без захвата всей рабочей
   папки. Коммит `0c6bcb9` унёс чужие частичные правки `src/office/redmine_mirror/__init__.py`
   и staged-удаление `alembic/`, и `develop` какое-то время не импортировал пакет зеркала.
   Alembic удалён намеренно (`059d64f`, решение пользователя В43-1), восстанавливать не нужно.

## Что изменилось вокруг зеркала (сверка 43, §9)

- Ключ Redmine уходит только по `https`, редиректы запрещены; токен шифруется
  `CONNECTIONS_SECRET_KEY`, без ключа админка токен не принимает (`3de6ff4`).
- `requirements.lock` пересобран (`6ace40b`): mcp 2.3.0, claude-agent-sdk 0.2.175, без alembic.
