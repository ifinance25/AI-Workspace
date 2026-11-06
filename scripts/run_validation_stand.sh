#!/usr/bin/env bash
# run_validation_stand.sh: тестовый стенд ручной валидации находок (экран «Прогоны»).
#
# Отдельная база и порт, рабочий стенд :8600 и его data/sessions.db не затрагиваются.
# Запускается scripts/run_office.py, как на сервере: без чата, терминала и файлов проектов.
#
#   bash scripts/run_validation_stand.sh              поднять в фоне (nohup, без TTY)
#   bash scripts/run_validation_stand.sh --install-daemon   macOS: LaunchAgent (KeepAlive)
#   bash scripts/run_validation_stand.sh --uninstall-daemon macOS: убрать LaunchAgent
#   bash scripts/run_validation_stand.sh --stop       остановить (и LaunchAgent, если был)
#   bash scripts/run_validation_stand.sh --status     жив ли стенд
#   VALSTAND_CONFIRM_RESET=1 bash scripts/run_validation_stand.sh --reset   всё с нуля
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAND_DIR="${VALSTAND_DIR:-$ROOT/data/validation-stand}"
HOST="${VALSTAND_HOST:-127.0.0.1}"
PORT="${VALSTAND_PORT:-8712}"
if [[ -n "${VALSTAND_PORT:-}" ]]; then
    echo "run_validation_stand: VALSTAND_PORT=$PORT (по умолчанию 8712; curl и URL ниже должны совпадать с этим портом)" >&2
fi
PACKAGE="${VALSTAND_PACKAGE:-$HOME/Documents/FACT/_рабочие_файлы/сопоставление_29102026_прогон4/out/package_RUN4-20261029.zip}"
PIDFILE="$STAND_DIR/stand.pid"
ACCOUNTS="$STAND_DIR/accounts.txt"
URL="http://$HOST:$PORT"
# curl по умолчанию уважает HTTP(S)_PROXY: запросы к 127.0.0.1 уходят в прокси
# и висят до таймаута, хотя uvicorn уже слушает порт. Обходим для проверки здоровья.
# Не передаём WEB_PORT в дочерний процесс: в config.yaml порт может быть ${WEB_PORT},
# тогда expandvars подставит его раньше, чем run_office.py применит --port (гонка и «health на другом порту»).
VALSTAND_HEALTH_MAX_TIME="${VALSTAND_HEALTH_MAX_TIME:-8}"
VALSTAND_HEALTH_CONNECT_TIMEOUT="${VALSTAND_HEALTH_CONNECT_TIMEOUT:-3}"
# Пауза после первого успешного health перед второй проверкой (ловит мгновенный crash).
VALSTAND_POST_HEALTH_DELAY="${VALSTAND_POST_HEALTH_DELAY:-1}"
# Сколько секунд после старта порт и pid должны оставаться валидными (самопроверка скрипта).
VALSTAND_STABILITY_SECONDS="${VALSTAND_STABILITY_SECONDS:-5}"
_curl_local_health() {
    curl -fsS --noproxy '*' --max-time "$VALSTAND_HEALTH_MAX_TIME" \
        --connect-timeout "$VALSTAND_HEALTH_CONNECT_TIMEOUT" "$URL/api/health"
}
LAUNCH_LABEL="${VALSTAND_LAUNCH_LABEL:-com.ai-workspace.validation-stand}"
PLIST_TMPL="$ROOT/scripts/launchd/com.ai-workspace.validation-stand.plist.in"
PLIST_DEST="${HOME}/Library/LaunchAgents/${LAUNCH_LABEL}.plist"

_is_darwin() {
    [[ "$(uname -s)" == Darwin ]]
}

# Загружен ли пользовательский LaunchAgent с меткой $LAUNCH_LABEL.
_launchd_loaded() {
    _is_darwin || return 1
    command -v launchctl >/dev/null 2>&1 || return 1
    launchctl list 2>/dev/null | awk 'NR>1 {print $3}' | grep -qx "$LAUNCH_LABEL"
}

_render_launchd_plist() {
    local out="$1"
    local jwt
    [[ -f "$STAND_DIR/jwt_secret" ]] || { echo "Нет $STAND_DIR/jwt_secret (сначала подготовка стенда)." >&2; return 1; }
    jwt="$(cat "$STAND_DIR/jwt_secret")"
    [[ -f "$PLIST_TMPL" ]] || { echo "Нет шаблона plist: $PLIST_TMPL" >&2; return 1; }
    sed \
        -e "s|@ROOT@|$ROOT|g" \
        -e "s|@STAND_DIR@|$STAND_DIR|g" \
        -e "s|@PYTHON@|$PY|g" \
        -e "s|@HOST@|$HOST|g" \
        -e "s|@PORT@|$PORT|g" \
        -e "s|@LABEL@|$LAUNCH_LABEL|g" \
        -e "s|@JWT_SECRET@|$jwt|g" \
        "$PLIST_TMPL" > "$out.tmp"
    mv "$out.tmp" "$out"
}

# PID процессов, слушающих TCP-порт $PORT (пусто, если порт свободен).
_listen_pids_on_port() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null | sort -u
        return 0
    fi
    echo "run_validation_stand: нужен lsof для проверки порта $PORT (macOS: встроен; Linux: пакет lsof)" >&2
    return 2
}

_is_our_run_office_pid() {
    local pid="$1" cmd
    [[ -n "$pid" ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    cmd="${cmd#"${cmd%%[![:space:]]*}"}"
    [[ -n "$cmd" ]] || return 1
    echo "$cmd" | grep -q run_office.py
}

# После --stop: порт должен быть свободен, либо слушать только наш run_office.py (тогда SIGTERM).
# Чужой процесс на порту: понятное сообщение и выход с ошибкой.
_ensure_port_free_before_start() {
    local max_rounds=40
    local round pid pids foreign saw_ours
    for round in $(seq 1 "$max_rounds"); do
        pids="$(_listen_pids_on_port)" || return 1
        [[ -z "${pids//[$'\t\n\r ']/}" ]] && return 0
        foreign=0
        saw_ours=0
        for pid in $pids; do
            if _is_our_run_office_pid "$pid"; then
                saw_ours=1
                echo "Порт $PORT ещё занят нашим run_office.py (pid $pid), отправляю SIGTERM…" >&2
                kill -TERM "$pid" 2>/dev/null || true
            else
                foreign=1
                echo "Порт $PORT занят другим процессом (pid $pid), не run_office.py этой стойки:" >&2
                ps -p "$pid" -o pid=,command= 2>/dev/null | sed 's/^/  /' >&2 || echo "  (процесс уже завершился)" >&2
            fi
        done
        if [[ "$foreign" -eq 1 ]]; then
            echo "Освободите порт $PORT или задайте другой: VALSTAND_PORT=… bash scripts/run_validation_stand.sh" >&2
            return 1
        fi
        if [[ "$saw_ours" -eq 1 ]]; then
            sleep 0.25
            continue
        fi
        sleep 0.25
    done
    echo "Порт $PORT не освободился за отведённое время. Слушатели:" >&2
    _listen_pids_on_port | while read -r pid; do
        [[ -n "$pid" ]] || continue
        ps -p "$pid" -o pid=,command= 2>/dev/null | sed 's/^/  /' >&2 || true
    done
    return 1
}

# Ожидание ответа /api/health; при провале: хвост журнала и код выхода 1.
_wait_for_health() {
    local attempt log_path="$STAND_DIR/stand.log"
    for attempt in $(seq 1 90); do
        if _curl_local_health >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.5
    done
    echo "Стенд не ответил по GET /api/health за отведённое время (curl, см. VALSTAND_HEALTH_*; при HTTP_PROXY без --noproxy localhost уходит в прокси)." >&2
    echo "Последние строки журнала $log_path:" >&2
    if [[ -f "$log_path" ]]; then
        tail -n 60 "$log_path" >&2
    else
        echo "  (файл журнала отсутствует)" >&2
    fi
    return 1
}

# После успешного health: pidfile не пустой, процесс жив и это run_office.py (отсекает гонки и «успех» не на том PID).
_verify_pidfile_matches_process() {
    local pid
    [[ -f "$PIDFILE" ]] || {
        echo "run_validation_stand: нет $PIDFILE после ожидания health." >&2
        return 1
    }
    pid="$(tr -cd '0-9' < "$PIDFILE" 2>/dev/null || true)"
    [[ -n "$pid" ]] || {
        echo "run_validation_stand: в $PIDFILE нет числового PID (повреждённый pidfile?)." >&2
        return 1
    }
    if ! _is_our_run_office_pid "$pid"; then
        echo "run_validation_stand: pid $pid из pidfile не похож на наш run_office.py (процесс умер или перезаписан)." >&2
        return 1
    fi
    return 0
}

# Кто слушает $PORT и похож на наш run_office.py: записать PID в pidfile (обходит stale PID от nohup без exec).
_refresh_pidfile_from_listener() {
    local pid
    for pid in $(_listen_pids_on_port); do
        [[ -n "$pid" ]] || continue
        if _is_our_run_office_pid "$pid"; then
            printf '%s\n' "$pid" > "$PIDFILE"
            return 0
        fi
    done
    return 1
}

# Процесс держит открытой именно базу стенда validation-stand (узко для --stop).
_pid_has_validation_stand_db() {
    local pid="$1"
    [[ -n "$pid" ]] || return 1
    lsof -p "$pid" 2>/dev/null | grep -qF "$STAND_DIR/sessions.db"
}

# Вторая проверка после health: пауза, повторный curl, pidfile и стабильность несколько секунд.
_verify_still_up() {
    local log_path="$STAND_DIR/stand.log"
    local deadline now pid
    sleep "$VALSTAND_POST_HEALTH_DELAY"
    if ! _curl_local_health >/dev/null 2>&1; then
        echo "run_validation_stand: после паузы ${VALSTAND_POST_HEALTH_DELAY}s сервер не ответил на GET /api/health." >&2
        echo "Последние строки журнала $log_path:" >&2
        [[ -f "$log_path" ]] && tail -n 60 "$log_path" >&2 || echo "  (файл журнала отсутствует)" >&2
        return 1
    fi
    if ! _verify_pidfile_matches_process; then
        echo "run_validation_stand: подправляю pidfile по слушателю порта $PORT…" >&2
        if ! _refresh_pidfile_from_listener; then
            echo "run_validation_stand: не удалось сопоставить PID с run_office.py на порту $PORT." >&2
            echo "Последние строки журнала $log_path:" >&2
            [[ -f "$log_path" ]] && tail -n 60 "$log_path" >&2 || echo "  (файл журнала отсутствует)" >&2
            return 1
        fi
    fi
    if [[ -z "${VALSTAND_STABILITY_SECONDS:-}" ]] || ! [[ "${VALSTAND_STABILITY_SECONDS}" =~ ^[0-9]+$ ]]; then
        VALSTAND_STABILITY_SECONDS=5
    fi
    deadline=$(( $(date +%s) + VALSTAND_STABILITY_SECONDS ))
    while [[ "$(date +%s)" -lt "$deadline" ]]; do
        if ! _curl_local_health >/dev/null 2>&1; then
            echo "run_validation_stand: сервер перестал отвечать до истечения ${VALSTAND_STABILITY_SECONDS}s стабильности." >&2
            echo "Последние строки журнала $log_path:" >&2
            [[ -f "$log_path" ]] && tail -n 60 "$log_path" >&2 || echo "  (файл журнала отсутствует)" >&2
            return 1
        fi
        pid="$(tr -cd '0-9' < "$PIDFILE" 2>/dev/null || true)"
        if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null || ! _is_our_run_office_pid "$pid"; then
            echo "run_validation_stand: процесс из pidfile ($pid) не жив или не run_office.py." >&2
            echo "Последние строки журнала $log_path:" >&2
            [[ -f "$log_path" ]] && tail -n 60 "$log_path" >&2 || echo "  (файл журнала отсутствует)" >&2
            return 1
        fi
        sleep 1
    done
    return 0
}

stop_stand() {
    local pid orphan
    if _launchd_loaded; then
        launchctl bootout "gui/$(id -u)/$LAUNCH_LABEL" 2>/dev/null || \
            launchctl bootout "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null || true
    fi
    if [[ -f "$PIDFILE" ]]; then
        pid="$(tr -cd '0-9' < "$PIDFILE" 2>/dev/null || true)"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && ps -p "$pid" -o command= 2>/dev/null | grep -q run_office.py; then
            kill -TERM "$pid" 2>/dev/null || true
            for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.25; done
        fi
        rm -f "$PIDFILE"
    fi
    # Остатки без pidfile: run_office.py с открытой БД этого стенда (SESSION_DATABASE_PATH → validation-stand).
    if command -v pgrep >/dev/null 2>&1; then
        while read -r orphan; do
            [[ -n "$orphan" ]] || continue
            if _pid_has_validation_stand_db "$orphan"; then
                echo "run_validation_stand: останавливаю оставшийся run_office.py (pid $orphan, $STAND_DIR/sessions.db)…" >&2
                kill -TERM "$orphan" 2>/dev/null || true
            fi
        done < <(pgrep -f "run_office.py" 2>/dev/null || true)
    fi
}

PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || { echo "Нет venv: $ROOT/.venv" >&2; exit 1; }

# Каталог стенда, опциональная сборка фронта, сид, jwt_secret.
prepare_stand() {
    mkdir -p "$STAND_DIR"
    chmod 700 "$STAND_DIR"

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
}

MODE=start
for arg in "$@"; do
    case "$arg" in
        --stop) MODE=stop ;;
        --status) MODE=status ;;
        --reset) MODE=reset ;;
        --install-daemon) MODE=install-daemon ;;
        --uninstall-daemon) MODE=uninstall-daemon ;;
        --help|-h)
            sed -n '2,17p' "$0"
            exit 0
            ;;
        *) echo "Неизвестный аргумент: $arg" >&2; exit 2 ;;
    esac
done

if [[ "$MODE" == "stop" ]]; then stop_stand; echo "Стенд остановлен"; exit 0; fi
if [[ "$MODE" == "status" ]]; then
    if _curl_local_health >/dev/null; then
        echo "Стенд жив: $URL"
        if _launchd_loaded; then
            echo "Режим: LaunchAgent $LAUNCH_LABEL (launchctl)"
        elif [[ -f "$PIDFILE" ]]; then
            echo "Режим: фоновой процесс (pid $(cat "$PIDFILE"))"
        fi
    else
        echo "Стенд не отвечает"
        exit 1
    fi
    exit 0
fi

if [[ "$MODE" == "uninstall-daemon" ]]; then
    _is_darwin || { echo "LaunchAgent только на macOS." >&2; exit 2; }
    stop_stand
    rm -f "$PLIST_DEST"
    echo "LaunchAgent $LAUNCH_LABEL удалён (plist: $PLIST_DEST)."
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

stop_stand
prepare_stand

if [[ "$MODE" == "install-daemon" ]]; then
    _is_darwin || { echo "LaunchAgent только на macOS (darwin)." >&2; exit 2; }
    _ensure_port_free_before_start || exit 1
    mkdir -p "$(dirname "$PLIST_DEST")"
    _render_launchd_plist "$PLIST_DEST"
    chmod 644 "$PLIST_DEST"
    # Снять job и по метке, и по пути plist (иначе bootstrap может не подхватить новый plist).
    launchctl bootout "gui/$(id -u)/$LAUNCH_LABEL" 2>/dev/null || true
    launchctl bootout "gui/$(id -u)" "$PLIST_DEST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST_DEST"
    launchctl enable "gui/$(id -u)/$LAUNCH_LABEL"
    launchctl kickstart -k "gui/$(id -u)/$LAUNCH_LABEL"
    # KeepAlive + первый импорт Python: иногда ответ на /api/health появляется не сразу.
    sleep 2
    _wait_for_health || exit 1
    sleep "$VALSTAND_POST_HEALTH_DELAY"
    if ! _curl_local_health >/dev/null 2>&1; then
        echo "run_validation_stand: LaunchAgent: после паузы сервер не ответил на GET /api/health." >&2
        exit 1
    fi
    echo "LaunchAgent загружен: $LAUNCH_LABEL"
    echo "plist: $PLIST_DEST"
    echo "Стенд: $URL/office/1/runs"
    echo "Остановка: bash scripts/run_validation_stand.sh --stop   или   bash scripts/run_validation_stand.sh --uninstall-daemon"
    exit 0
fi

_ensure_port_free_before_start || exit 1

# Если стенд уже поднят через LaunchAgent, не дублируем процесс.
if _launchd_loaded; then
    _wait_for_health || exit 1
    echo "Стенд уже работает под LaunchAgent ($LAUNCH_LABEL): $URL/office/1/runs"
    echo "Учётки (логины и пароли): $ACCOUNTS"
    exit 0
fi

# Из каталога стенда: .env репозитория с настоящими секретами не читается.
# nohup bash -c 'exec python …': $! это PID uvicorn/python. Прямой «nohup python» на macOS давал PID краткоживущего nohup, pidfile устаревал.
# stdin /dev/null: без управляющего TTY; disown снимает job с оболочки (в том числе встроенный терминал IDE).
OFFICE_EXEC_CMD=$(printf 'exec %q %q --host %q --port %q' "$PY" "$ROOT/scripts/run_office.py" "$HOST" "$PORT")
cd "$STAND_DIR" || exit 1
{
    if command -v setsid >/dev/null 2>&1 && ! _is_darwin; then
        setsid env -u WEB_PORT PYTHONPATH="$ROOT" SESSION_DATABASE_PATH="$STAND_DIR/sessions.db" \
            WEB_JWT_SECRET="$(cat "$STAND_DIR/jwt_secret")" ADMIN_LOGIN= ADMIN_PASSWORD= \
            nohup bash -c "$OFFICE_EXEC_CMD" \
            >> "$STAND_DIR/stand.log" 2>&1 < /dev/null &
    else
        env -u WEB_PORT PYTHONPATH="$ROOT" SESSION_DATABASE_PATH="$STAND_DIR/sessions.db" \
            WEB_JWT_SECRET="$(cat "$STAND_DIR/jwt_secret")" ADMIN_LOGIN= ADMIN_PASSWORD= \
            nohup bash -c "$OFFICE_EXEC_CMD" \
            >> "$STAND_DIR/stand.log" 2>&1 < /dev/null &
    fi
    printf '%s\n' "$!" > "$PIDFILE"
} || exit 1
disown -a 2>/dev/null || true
cd "$ROOT" || exit 1

_wait_for_health || exit 1
_verify_still_up || exit 1

echo "Стенд поднят: $URL/office/1/runs"
echo "Учётки (логины и пароли): $ACCOUNTS"
echo "Остановка только вручную, когда стенд больше не нужен (не шаг проверки «поднял и curl»): bash scripts/run_validation_stand.sh --stop"
echo "На macOS для автоперезапуска: bash scripts/run_validation_stand.sh --install-daemon"
