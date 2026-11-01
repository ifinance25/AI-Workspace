# Сервер ручной валидации на VPS tatnet

Документ для оператора. Любое действие на сервере делается только по подтверждению владельца: рядом с сервисом работают база знаний и MCP.

## Состояние выката на 2026-11-01

Сделано на VPS `fact@185.152.82.63` (`fact-basa`), ничего из контура `fakt` (база знаний, MCP, nginx) не менялось и не перезапускалось:

- образ `fakt-runs:6769210` (с экраном «Команда», `/office/:id/members`) собран из закоммиченного кода (не из рабочей папки) и загружен напрямую; обновлён 2026-11-01 после разовой копии, данные целы (82 находки);
- каталоги `/srv/fakt/validation/data`, `/srv/fakt/validation-backups`, `/opt/fakt-runs`; секреты в `/srv/fakt/validation/runs.env` (root, 0600), созданы на сервере;
- контейнер `fakt-runs` (проект Compose `fakt-runs`, сеть `fakt_runs-net` без выхода в интернет, файловая система только для чтения, без привилегий) работает и здоров;
- ночные копии включены (`fakt-validation-backup.timer`, 03:38 UTC, 14 дней), разовая копия проверена;
- пакет прогона № 4 загружен: 82 находки, 139 правок, 408 файлов (48 МБ), проект «ФАКТ: валидация прогона № 4».

Не сделано, ждёт владельца:

- **DNS-запись `runs.pm-workspace.ru`** (A на `185.152.82.63`) и сертификат. Без неё публичного адреса нет.
- **Подключение к nginx контура.** Контур `fakt` собирается скриптом выката из другого репозитория (`ФАКТ.Диджитал/deploy/kb-mcp`), каждый релиз лежит в новом каталоге. Ручная правка текущего релиза пропала бы при следующем выкате, поэтому блоки из `nginx-runs.conf` и сеть `fakt_runs-net` нужно внести в тот репозиторий и выкатить его штатно.

До этого сервис открывается только через SSH-туннель: `bash deploy/tatnet-office/open-tunnel.sh` (адрес `http://localhost:8613/office/1/runs`), пароль администратора `bash deploy/tatnet-office/open-tunnel.sh --show-admin`, закрыть `--close`. Первый вход под `admin`, пароль после входа сменить.

Роли: администратор создаёт учётки в разделе «Администрирование», менеджер проекта или администратор вводит логин и роль на экране «Команда» (`/office/:id/members`). Проект и создателя-менеджера заводит тот, кто первым создал проект офиса.

## Что ставится

Контейнер `fakt-runs` рядом с контуром `fakt` (`/opt/fakt-knowledge-base`, проект Compose `fakt`). Адрес `https://runs.pm-workspace.ru`. Только проектный офис и валидация: нет Claude, Telegram, терминала, файлов проектов, загрузок и чата. Контейнер сидит во внутренней сети `fakt_runs-net` без выхода в интернет, порт наружу не публикуется, снаружи его открывает nginx контура.

Данные: `/srv/fakt/validation/data` (база `sessions.db` и папка `office_validation/` с markdown, снимками и PDF). Копии: `/srv/fakt/validation-backups`, 14 дней.

## Перед началом

1. Проверить место: `df -h / /srv/fakt`. Для образа нужно не меньше 25 ГиБ свободных на корневом диске (порог из `deploy/kb-mcp/VPS-REMAINING-STEPS-RUNBOOK.md`). Для данных: прогон № 4 занимает около 50 МБ.
2. Узнать архитектуру сервера: `uname -m`. Команда сборки ниже для `linux/amd64`.
3. Сделать копию того, что будем менять: `sudo cp -a /opt/fakt-knowledge-base /opt/fakt-knowledge-base.bak-$(date +%Y%m%d)`.
4. Завести DNS-запись `runs.pm-workspace.ru` (A на IP сервера) и дождаться ответа `dig +short runs.pm-workspace.ru`.

## Шаги

Команды без пометки идут на машине разработки из корня клона, команды с `sudo` на VPS.

1. Собрать образ: `docker build --platform linux/amd64 -f deploy/tatnet-office/Dockerfile -t fakt-runs:$(git rev-parse --short HEAD) .`
2. Передать на сервер без реестра: `docker save fakt-runs:<версия> | gzip | ssh fact@185.152.82.63 'gunzip | sudo docker load'`
3. Создать каталоги: `sudo install -d -m 0750 -o 1001 -g 1001 /srv/fakt/validation/data` и `sudo install -d -m 0700 /srv/fakt/validation-backups`.
4. Создать `/srv/fakt/validation/runs.env` по шаблону `deploy/tatnet-office/runs.env.example`, владелец root, права 0600. Секрет сгенерировать на сервере: `openssl rand -hex 32`. Значения не вставлять в чат, в Git и в историю командной строки (вводить через редактор).
5. Скопировать `compose.yaml` в `/opt/fakt-runs/`, убрать из копии блок `build:` (его контекст `../..` указывал бы на корень диска) и запустить: `sudo env RELEASE=<версия> docker compose -f /opt/fakt-runs/compose.yaml up -d --no-build`. Проверить: `sudo docker compose ps` (состояние `healthy`).
6. Выпустить сертификат `runs.pm-workspace.ru` тем же способом, что для остальных доменов (certbot, webroot `/srv/acme`), положить в `/srv/fakt/tls/runs.pm-workspace.ru/`.
7. Подключить nginx. В `deploy/kb-mcp/compose.yaml` добавить сервису `nginx` сеть `runs-net` и объявить её внешней:
   ```yaml
   networks: [public, web-net, mcp-net, runs-net]
   ...
   networks:
     runs-net: {external: true, name: fakt_runs-net}
   ```
   В `deploy/kb-mcp/nginx/conf.d/fakt.conf` добавить блоки из `deploy/tatnet-office/nginx-runs.conf`, в `nginx.conf` зону `limit_req_zone $binary_remote_addr zone=fakt_login:10m rate=10r/m;`. Сначала проверить конфигурацию, потом перезагружать: `sudo docker compose exec nginx nginx -t`, затем `sudo docker compose up -d nginx`. Пересоздание nginx на секунды прерывает `pm-workspace.ru` и `mcp.pm-workspace.ru`: делать в тихое время.
8. Копии: `sudo install -m 0755 scripts/backup_office.sh /opt/fakt-runs/backup_office.sh`, затем юниты `fakt-validation-backup.service` и `.timer` в `/etc/systemd/system/` и `sudo systemctl enable --now fakt-validation-backup.timer`. Проверить вручную: `sudo systemctl start fakt-validation-backup.service` и `ls -l /srv/fakt/validation-backups`.

## Проверка после выката

- `curl -sI https://runs.pm-workspace.ru/api/health` отвечает 200.
- `curl -s -o /dev/null -w '%{http_code}' https://runs.pm-workspace.ru/api/files/tree` отвечает 404, `/api/ssh` тоже 404.
- `https://pm-workspace.ru` и `https://mcp.pm-workspace.ru/mcp` работают как до выката (проверка MCP по `docs/MCP-ACCEPTANCE-2026-10-29.md` репозитория базы знаний).
- Вход первым администратором, смена пароля, создание проекта офиса, добавление участников с ролями. Заказчика заводить отдельной учёткой и проверить, что раздел «Прогоны» отвечает 403.
- Загрузить пакет прогона № 4 кнопкой «Загрузить прогон» (менеджер проекта). Ожидаем 82 находки, 139 правок, 6 PDF.

## Пакет прогона № 4

Собирается на машине разработки: `cd "/Users/ifinance/Documents/FACT/_рабочие_файлы/сопоставление_29102026_прогон4/evidence" && python3 build_package4.py`. Результат `out/package_RUN4-20261029.zip`, около 49 МБ. nginx пропускает до 128 МБ, приложение до 120 МБ.

## Откат

1. `sudo docker compose -f /opt/fakt-runs/compose.yaml down` останавливает сервис. Данные в `/srv/fakt/validation/data` остаются.
2. Убрать из `fakt.conf` блоки `runs.pm-workspace.ru`, сеть `runs-net` из nginx, повторить `nginx -t` и `up -d nginx`.
3. Вернуть копию контура из `/opt/fakt-knowledge-base.bak-<дата>`, если менялось что-то ещё.

## Восстановление из копии

Остановить контейнер: `sudo docker compose -f /opt/fakt-runs/compose.yaml stop runs`. Затем распаковать архив во временную папку, положить `sessions.db` в `/srv/fakt/validation/data/` (удалив рядом `sessions.db-wal` и `sessions.db-shm`), распаковать `office_validation.tar` в ту же папку, `chown -R 1001:1001`, запустить контейнер. Markdown можно пересобрать из базы, снимки и PDF только из копии.

## Что не закрыто

- Внешней копии нет. При потере диска сервера решения людей пропадут вместе с локальными копиями. Нужно решение владельца: куда класть зашифрованную копию.
- Журнал входа и сессии живут в той же базе: лимит попыток входа держит nginx (10 в минуту на адрес) и приложение.
- Сканер секретов и личных данных работает по образцам. Это страховка, а не псевдонимизация.
- Выгрузка markdown для внешней модели закрыта, пока менеджер проекта не включит её галочкой на экране «Прогоны». Включённая выгрузка отдаёт цитаты документов заказчика внешнему получателю: решает владелец данных и юрист.
