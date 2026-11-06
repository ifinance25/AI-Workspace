#!/usr/bin/env bash
# run_validation_stand.sh: тестовый стенд ручной валидации находок (экран «Прогоны»).
#
# Отдельная база и порт, рабочий стенд :8600 и его data/sessions.db не затрагиваются.
# Запускается scripts/run_office.py, как на сервере: без чата, терминала и файлов проектов.
#
#   bash scripts/run_validation_stand.sh            поднять (при первом запуске наполнить)
#   bash scripts/run_validation_stand.sh --stop     остановить
#   bash scripts/run_validation_stand.sh --status   жив ли стенд
#   VALSTAND_CONFIRM_RESET=1 bash scripts/run_validation_stand.sh --reset   всё с нуля
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAND_DIR="${VALSTAND_DIR:-$ROOT/data/validation-stand}"
HOST="${VALSTAND_HOST:-127.0.0.1}"
PORT="${VALSTAND_PORT:-8612}"
PACKAGE="${VALSTAND_PACKAGE:-$HOME/Documents/FACT/_рабочие_файлы/сопоставление_29102026_прогон4/out/package_RUN4-20261029.zip}"
PIDFILE="$STAND_DIR/stand.pid"
ACCOUNTS="$STAND_DIR/accounts.txt"
URL="http://$HOST:$PORT"

stop_stand() {
    if [[ -f "$PIDFILE" ]]; then
        pid="$(cat "$PIDFILE")"
        if kill -0 "$pid" 2>/dev/null && ps -p "$pid" -o command= | grep -q run_office.py; then
            kill "$pid" 2>/dev/null || true
            for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
        fi
        rm -f "$PIDFILE"
    fi
}

MODE=start
for arg in "$@"; do
    case "$arg" in
        --stop) MODE=stop ;;
        --status) MODE=status ;;
        --reset) MODE=reset ;;
        --help|-h) sed -n 2,11p "$0"; exit 0 ;;
        *) echo "Неизвестный аргумент: $arg" >&2; exit 2 ;;
    esac
done

if [[ "$MODE" == "stop" ]]; then stop_stand; echo "Стенд остановлен"; exit 0; fi
if [[ "$MODE" == "status" ]]; then
    if curl -fs --max-time 3 "$URL/api/health" >/dev/null; then echo "Стенд жив: $URL"; else echo "Стенд не отвечает"; exit 1; fi
    exit 0
fi
if [[ "$MODE" == "reset" ]]; then
    if [[ "${VALSTAND_CONFIRM_RESET:-0}" != "1" ]]; then
        echo "Сброс удалит базу, файлы прогона и учётки стенда $STAND_DIR." >&2
        echo "Подтвердите: VALSTAND_CONFIRM_RESET=1 bash scripts/run_validation_stand.sh --reset" >&2
        exit 2
    fi
    stop_stand
    # Удаляется только каталог стенда: рабочая data/sessions.db лежит выше и не затрагивается.
    case "$STAND_DIR" in */validation-stand|*/validation-stand/) rm -rf "$STAND_DIR" ;; *)
        echo "Каталог стенда должен называться validation-stand: $STAND_DIR" >&2; exit 2 ;; esac
fi

PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "Нет venv: $ROOT/.venv" >&2; exit 1; }

stop_stand
mkdir -p "$STAND_DIR"; chmod 700 "$STAND_DIR"

WEB_DIST="$ROOT/web/dist/index.html"
if [[ "${VALSTAND_SKIP_WEB_BUILD:-0}" != "1" ]]; then
    if [[ ! -f "$WEB_DIST" ]] || find "$ROOT/web/src" -type f -newer "$WEB_DIST" -print -quit | grep -q .; then
        echo "Сборка фронта (web/src новее web/dist)…" >&2
        (cd "$ROOT/web" && npm run build >/dev/null)
    fi
fi

if [[ ! -s "$STAND_DIR/sessions.db" ]]; then
    echo "Первый запуск: наполняю стенд…" >&2
    (cd "$STAND_DIR" && PYTHONPATH="$ROOT" "$PY" "$ROOT/scripts/seed_validation_stand.py" \
        --data-dir "$STAND_DIR" --package "$PACKAGE" --accounts-file "$ACCOUNTS")
fi

[[ -s "$STAND_DIR/jwt_secret" ]] || { umask 077; openssl rand -hex 32 > "$STAND_DIR/jwt_secret"; }

# Из каталога стенда: .env репозитория с настоящими секретами не читается.
# Без подоболочки вокруг nohup: при выходе subshell bash по умолчанию шлёт SIGHUP
# фоновым job в этой группе; nohup обычно спасает, но надёжнее не зависеть от окружения IDE.
cd "$STAND_DIR" || exit 1
env PYTHONPATH="$ROOT" SESSION_DATABASE_PATH="$STAND_DIR/sessions.db" \
    WEB_JWT_SECRET="$(cat "$STAND_DIR/jwt_secret")" ADMIN_LOGIN= ADMIN_PASSWORD= \
    nohup "$PY" "$ROOT/scripts/run_office.py" --host "$HOST" --port "$PORT" \
    > "$STAND_DIR/stand.log" 2>&1 < /dev/null &
echo $! > "$PIDFILE"
cd "$ROOT" || exit 1

for _ in $(seq 1 40); do
    curl -fs --max-time 2 "$URL/api/health" >/dev/null 2>&1 && break
    sleep 0.5
done
curl -fs --max-time 3 "$URL/api/health" >/dev/null || { echo "Стенд не поднялся, журнал: $STAND_DIR/stand.log" >&2; exit 1; }

echo "Стенд поднят: $URL/office/1/runs"
echo "Учётки (логины и пароли): $ACCOUNTS"
echo "Остановка только вручную, когда стенд больше не нужен (не шаг проверки «поднял и curl»): bash scripts/run_validation_stand.sh --stop"
