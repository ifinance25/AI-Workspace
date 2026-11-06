# Тестовый стенд ручной валидации

Отдельный стенд для проверки экрана «Прогоны». Рабочий стенд `:8600` и его `data/sessions.db` не затрагиваются.

## Запуск (по умолчанию)

```bash
bash scripts/run_validation_stand.sh            # поднять в фоне (без привязки к терминалу IDE)
bash scripts/run_validation_stand.sh --status   # жив ли и как поднят (pid или LaunchAgent)
bash scripts/run_validation_stand.sh --stop     # остановить (снимает и LaunchAgent, если был)
VALSTAND_CONFIRM_RESET=1 bash scripts/run_validation_stand.sh --reset   # всё с нуля
```

Адрес `http://127.0.0.1:8712/office/1/runs`. Порт меняет `VALSTAND_PORT`, каталог данных `VALSTAND_DIR` (имя каталога должно оканчиваться на `validation-stand`), пакет прогона `VALSTAND_PACKAGE`, хост `VALSTAND_HOST`. Фронт пересобирается сам, если `web/src` новее `web/dist`.

Перед стартом скрипт останавливает прежний экземпляр, проверяет порт (`lsof`) и ждёт `GET /api/health` (внутри скрипта curl с `--noproxy '*'`, чтобы при заданном `HTTP_PROXY` запрос к `127.0.0.1` не уходил в прокси). Таймауты: `VALSTAND_HEALTH_MAX_TIME` (по умолчанию 8 с) и `VALSTAND_HEALTH_CONNECT_TIMEOUT` (3 с). После первого успеха: пауза `VALSTAND_POST_HEALTH_DELAY` (по умолчанию 1 с), повторный health, при необходимости обновление `stand.pid` по слушателю порта, затем проверка стабильности `VALSTAND_STABILITY_SECONDS` (по умолчанию 5 с: curl и живой PID). При ошибке код выхода 1 и хвост `data/validation-stand/stand.log`.

### Почему стенд «пропадал»

1. **Сценарий агента:** строка «остановите вручную» иногда выполнялась как шаг чек-листа (`--stop`). Диагностика: `--status`. Стоп только когда стенд сознательно не нужен.

2. **Сессия терминала IDE:** фоновый job иногда получал сигналы при закрытии панели. В скрипте: `nohup`, перенаправление stdin на `/dev/null`, `disown`; на Linux без macOS дополнительно оборачивается `setsid` (новая сессия).

3. **Устаревший PID в `stand.pid` (macOS):** раньше в pidfile попадал краткоживущий процесс `nohup`, а не Python. Запуск через `nohup bash -c 'exec python …'`, плюс сверка PID с процессом на порту после health.

4. **Падение процесса:** смотрите `stand.log`. Для постоянной работы на macOS удобнее LaunchAgent ниже.

## macOS: LaunchAgent (устойчивый режим)

Один раз установить службу пользователя (`KeepAlive`, автоперезапуск). Шаблон: `scripts/launchd/com.ai-workspace.validation-stand.plist.in`. Секреты репозитория в plist не кладутся: в окружение подставляется только `WEB_JWT_SECRET` из `data/validation-stand/jwt_secret` (файл создаётся скриптом).

```bash
cd /path/to/AI-Workspace
bash scripts/run_validation_stand.sh --install-daemon
```

Что делает команда: готовит каталог стенда (сборка фронта при необходимости, сид БД, `jwt_secret`), пишет `~/Library/LaunchAgents/com.ai-workspace.validation-stand.plist`, выполняет `launchctl bootstrap`, `enable`, `kickstart`, ждёт health.

Своя метка (если нужно несколько стендов): `VALSTAND_LAUNCH_LABEL=com.example.other bash scripts/run_validation_stand.sh --install-daemon`.

Убрать службу и plist:

```bash
bash scripts/run_validation_stand.sh --uninstall-daemon
```

Ручная проверка (после установки):

```bash
launchctl print "gui/$(id -u)/com.ai-workspace.validation-stand"
curl -fsS --noproxy '*' http://127.0.0.1:8712/api/health
```

Остановка без удаления plist: `bash scripts/run_validation_stand.sh --stop` (снимет LaunchAgent с текущей сессии). Чтобы снова поднять после `--stop` без ручного `bootstrap`: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ai-workspace.validation-stand.plist` или снова `--install-daemon`.

## Что внутри

Сервер поднимается тем же входом, что на tatnet: `scripts/run_office.py`, без чата, терминала и файлов проектов. Данные лежат в `data/validation-stand/` (в Git не входят): база, файлы прогона, журнал `stand.log`, секрет сессий и файл `accounts.txt` с логинами и паролями (права 0600, пароли случайные).

Наполнение (`scripts/seed_validation_stand.py`): проект «ФАКТ: валидация прогона № 4» с пакетом из 82 находок, четыре готовых решения (R4-001 правки внесены, R4-002 отклонена, R4-003 на уточнение, R4-004 подтверждена), чужой проект для проверки изоляции.

## Учётки и ожидаемое поведение

| Логин | Роль | Что должно быть |
|---|---|---|
| `lead` | менеджер проекта | кнопки статуса, загрузка прогона, галочка вывоза, «Скачать markdown» |
| `tester`, `analyst`, `sysanalyst` | тестировщик, бизнес- и системный аналитик | кнопки статуса, без загрузки и вывоза |
| `developer`, `observer` | разработчик, наблюдатель | смотрят, вместо кнопок пояснение |
| `customer` | представитель заказчика | «Раздел закрыт для заказчика» |
| `other` | менеджер чужого проекта | проект не открывает (404) |
| `admin` | администратор системы, не участник | смотрит и управляет, статус не ставит |

Что проверить глазами: вкладка «Реестр прогонов» (дата, тип сравнения, документы, версия серии, счётчики статусов, «Разобрано» / «Прогон можно закрыть»), список и фильтры карточек, карточка (суть, таблица «Было, Стало», снимки, ссылки на страницы PDF), клик по снимку (карусель: заголовок документа и страница, стрелки, точки, счётчик), решение каждой кнопкой, вкладка «Статистика», узкий экран. Манифест пакета: `docs/validation-package-manifest.md`. Просмотр PDF рассчитан на встроенный просмотрщик обычного Chrome или Safari.
