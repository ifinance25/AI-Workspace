#!/usr/bin/env bash
# run_stand.sh — локальный стенд из дампа БД, затем scripts/run_web.py.
#
# Всегда restore из data/dumps/. На прод за дампом не ходит.
#
#   bash scripts/run_stand.sh
#   bash scripts/run_stand.sh --restore-only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${STAND_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
HOST="${STAND_HOST:-127.0.0.1}"
PORT="${STAND_PORT:-8600}"
RESTORE_ONLY=0

for arg in "$@"; do
    case "$arg" in
        --restore-only) RESTORE_ONLY=1 ;;
        --help|-h)
            cat <<EOF
Локальный стенд AI-Workspace из дампа SQLite.

  bash scripts/run_stand.sh              восстановить БД и поднять веб
  bash scripts/run_stand.sh --restore-only   только восстановить БД

По умолчанию: http://127.0.0.1:8600
Дамп: data/dumps/sessions.latest.db (см. data/dumps/README.md)
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

export STAND_ROOT="$ROOT"
export STAND_PORT="$PORT"
bash "$SCRIPT_DIR/restore_stand_db.sh"

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

cd "$ROOT"
exec "$PY" "$ROOT/scripts/run_web.py" --host "$HOST" --port "$PORT"
