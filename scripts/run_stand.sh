#!/usr/bin/env bash
# run_stand.sh — локальный стенд: рабочая SQLite + scripts/run_web.py.
#
# По умолчанию НЕ затирает data/sessions.db дампом (токены, офис, сиды сохраняются).
# Полный сброс из data/dumps/: STAND_FORCE_RESTORE=1 или bash scripts/run_stand.sh --restore
#
#   bash scripts/run_stand.sh
#   bash scripts/run_stand.sh --restore-only
#   STAND_FORCE_RESTORE=1 bash scripts/run_stand.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${STAND_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
HOST="${STAND_HOST:-127.0.0.1}"
PORT="${STAND_PORT:-8600}"
RESTORE_ONLY=0
FORCE_RESTORE=0

for arg in "$@"; do
    case "$arg" in
        --restore-only) RESTORE_ONLY=1 ;;
        --restore) FORCE_RESTORE=1 ;;
        --help|-h)
            cat <<EOF
Локальный стенд AI-Workspace.

  bash scripts/run_stand.sh                 поднять веб, БД не трогать
  bash scripts/run_stand.sh --restore       сброс БД из дампа (нужен STAND_CONFIRM_RESTORE=1), затем веб
  bash scripts/run_stand.sh --restore-only  только restore (или STAND_FORCE_RESTORE=1)

По умолчанию: http://127.0.0.1:8600
Дамп для сброса: data/dumps/sessions.latest.db (см. data/dumps/README.md)
Пропустить сборку фронта: STAND_SKIP_WEB_BUILD=1 bash scripts/run_stand.sh
EOF
            exit 0
            ;;
        *)
            echo "Неизвестный аргумент: $arg" >&2
            echo "Справка: bash scripts/run_stand.sh --help" >&2
            exit 2
            ;;
    esac
done

if [[ "${STAND_FORCE_RESTORE:-0}" == "1" ]]; then
    FORCE_RESTORE=1
fi

if [[ "$FORCE_RESTORE" == "1" ]] && [[ "${STAND_CONFIRM_RESTORE:-0}" != "1" ]]; then
    echo "Сброс БД уничтожит локальные настройки (Redmine, офис, чаты)." >&2
    echo "Подтвердите: STAND_CONFIRM_RESTORE=1 bash scripts/run_stand.sh --restore" >&2
    exit 2
fi

export STAND_ROOT="$ROOT"
export STAND_PORT="$PORT"

bash "$SCRIPT_DIR/restore_stand_db.sh" --stop-only

TARGET="$(bash "$SCRIPT_DIR/restore_stand_db.sh" --print-db-path)"
if [[ "$FORCE_RESTORE" == "1" ]]; then
    export STAND_FORCE_RESTORE=1
    bash "$SCRIPT_DIR/restore_stand_db.sh" --force
elif [[ ! -s "$TARGET" ]]; then
    echo "Первый запуск: восстановление БД из дампа…" >&2
    bash "$SCRIPT_DIR/restore_stand_db.sh"
else
    echo "БД без изменений: $TARGET" >&2
fi

if [[ "$RESTORE_ONLY" == "1" ]]; then
    exit 0
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PY="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
    PY="$ROOT/.venv/Scripts/python.exe"
else
    echo "Нет venv: создайте .venv в корне клона и поставьте requirements.txt" >&2
    exit 1
fi

PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" "$PY" "$ROOT/scripts/seed_redmine_lookups.py" --if-empty

WEB_DIST="$ROOT/web/dist/index.html"
if [[ "${STAND_SKIP_WEB_BUILD:-0}" != "1" ]]; then
    need_build=0
    if [[ ! -f "$WEB_DIST" ]]; then
        need_build=1
    elif find "$ROOT/web/src" -type f -newer "$WEB_DIST" -print -quit 2>/dev/null | grep -q .; then
        need_build=1
    fi
    if [[ "$need_build" == "1" ]]; then
        echo "Сборка фронта (web/src новее web/dist)…" >&2
        (cd "$ROOT/web" && npm run build)
    fi
fi

cd "$ROOT"
exec "$PY" "$ROOT/scripts/run_web.py" --host "$HOST" --port "$PORT"
