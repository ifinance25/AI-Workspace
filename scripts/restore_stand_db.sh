#!/usr/bin/env bash
# restore_stand_db.sh — перед локальным стендом восстановить SQLite из дампа.
#
# Дамп лежит в data/dumps/ (не в git: сессии и ключи). С прода НЕ ходим:
# если файла нет, выходим с инструкцией. Обновление дампа: только по явной
# просьбе пользователя, scripts/fetch_stand_dump.sh.
#
# Использование (из корня git-клона):
#   bash scripts/restore_stand_db.sh
#   STAND_PORT=8600 bash scripts/restore_stand_db.sh
#
# Переменные:
#   STAND_ROOT       корень клона (по умолчанию: родитель scripts/)
#   STAND_DUMP_DIR   папка дампов (по умолчанию: $STAND_ROOT/data/dumps)
#   STAND_DUMP_FILE  явный путь к .db, иначе sessions.latest.db / newest dated
#   STAND_DB_PATH    рабочая SQLite стенда (иначе SESSION_DATABASE_PATH из .env
#                    или data/sessions.db)
#   STAND_PORT       порт стенда, который нужно остановить перед подменой
#                    (по умолчанию 8600)
#   STAND_SKIP_STOP  1: не трогать процесс (только для тестов)
#   STAND_PROJECTS_DIR  локальный PROJECTS_DIR (иначе из .env). После copy
#                    пути /var/lib/... в рабочей БД переписываются сюда,
#                    каталоги проектов создаются. Оригинал дампа не трогаем.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${STAND_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
DUMP_DIR="${STAND_DUMP_DIR:-$ROOT/data/dumps}"
PORT="${STAND_PORT:-8600}"

die() {
    printf '%s\n' "$*" >&2
    exit 1
}

read_env_key() {
    local key="$1"
    local envf="$ROOT/.env"
    local val=""
    if [[ -f "$envf" ]]; then
        val="$(awk -F= -v k="$key" '
            $0 ~ "^[[:space:]]*" k "=" {
                sub("^[[:space:]]*" k "=", "")
                gsub(/\r$/, "")
                print
                exit
            }
        ' "$envf")"
        val="${val%\"}"
        val="${val#\"}"
        val="${val%\'}"
        val="${val#\'}"
    fi
    printf '%s' "$val"
}

abs_from_root() {
    local val="$1"
    if [[ "$val" = /* ]]; then
        printf '%s' "$val"
    else
        printf '%s' "$ROOT/$val"
    fi
}

read_session_db_path() {
    local val
    val="$(read_env_key SESSION_DATABASE_PATH)"
    if [[ -n "${STAND_DB_PATH:-}" ]]; then
        TARGET="$STAND_DB_PATH"
    elif [[ -n "$val" ]]; then
        TARGET="$(abs_from_root "$val")"
    else
        TARGET="$ROOT/data/sessions.db"
    fi
}

read_projects_dir() {
    local val
    if [[ -n "${STAND_PROJECTS_DIR:-}" ]]; then
        PROJECTS_DIR="$(abs_from_root "$STAND_PROJECTS_DIR")"
    else
        val="$(read_env_key PROJECTS_DIR)"
        if [[ -n "$val" ]]; then
            PROJECTS_DIR="$(abs_from_root "$val")"
        else
            PROJECTS_DIR=""
        fi
    fi
    PROJECTS_DIR="${PROJECTS_DIR%/}"
}

resolve_dump() {
    if [[ -n "${STAND_DUMP_FILE:-}" ]]; then
        DUMP="$STAND_DUMP_FILE"
        return 0
    fi
    local candidate
    for candidate in "$DUMP_DIR/sessions.latest.db" "$DUMP_DIR/sessions.db"; do
        if [[ -e "$candidate" ]]; then
            DUMP="$candidate"
            return 0
        fi
    done
    local newest=""
    local f
    shopt -s nullglob
    for f in "$DUMP_DIR"/sessions-????-??-??.db; do
        newest="$f"
    done
    shopt -u nullglob
    if [[ -n "$newest" ]]; then
        DUMP="$newest"
        return 0
    fi
    DUMP=""
    return 1
}

print_missing_dump() {
    cat >&2 <<EOF
Нет дампа БД для локального стенда.

Папка дампов: $DUMP_DIR
Ожидается один из файлов:
  sessions.latest.db
  sessions.db
  sessions-YYYY-MM-DD.db

Свежий дамп с прода скрипт сам не снимает.
Когда пользователь явно попросит обновить дамп:
  STAND_DUMP_FETCH=1 bash scripts/fetch_stand_dump.sh

Подробности: data/dumps/README.md
EOF
}

stop_stand() {
    [[ "${STAND_SKIP_STOP:-}" == "1" ]] && return 0
    local pids=""
    local pid
    if command -v lsof >/dev/null 2>&1; then
        pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
    fi
    if [[ -z "$pids" ]] && command -v pgrep >/dev/null 2>&1; then
        pids="$(pgrep -f 'scripts/run_web.py' 2>/dev/null || true)"
    fi
    [[ -z "$pids" ]] && return 0
    echo "Останавливаю стенд на порту $PORT перед подменой SQLite (pid: $pids)."
    for pid in $pids; do
        kill "$pid" 2>/dev/null || true
    done
    local i
    for i in $(seq 1 20); do
        local alive=0
        for pid in $pids; do
            if kill -0 "$pid" 2>/dev/null; then
                alive=1
            fi
        done
        [[ "$alive" == "0" ]] && break
        sleep 0.25
    done
    for pid in $pids; do
        kill -9 "$pid" 2>/dev/null || true
    done
}

copy_dump() {
    local src="$1"
    local dst="$2"
    mkdir -p "$(dirname "$dst")"
    rm -f "${dst}-wal" "${dst}-shm"
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$src" ".backup '$dst'"
    else
        cp "$src" "$dst"
    fi
    if command -v sqlite3 >/dev/null 2>&1; then
        sqlite3 "$dst" "PRAGMA integrity_check;" >/dev/null \
            || die "Дамп скопирован, но integrity_check не прошёл: $dst"
    fi
}

read_session_db_path
if ! resolve_dump || [[ ! -e "$DUMP" ]]; then
    print_missing_dump
    exit 1
fi
if [[ ! -s "$DUMP" ]]; then
    die "Дамп пустой: $DUMP"
fi

stop_stand
copy_dump "$DUMP" "$TARGET"
echo "Восстановлено: $DUMP -> $TARGET"
