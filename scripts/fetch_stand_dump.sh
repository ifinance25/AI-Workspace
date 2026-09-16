#!/usr/bin/env bash
# fetch_stand_dump.sh — снять SQLite с прода в data/dumps/.
#
# Запускать ТОЛЬКО по явной просьбе пользователя. restore/run_stand этот
# скрипт не вызывают.
#
#   STAND_DUMP_FETCH=1 STAND_DUMP_SSH=user@host bash scripts/fetch_stand_dump.sh
#
# STAND_DUMP_SSH: user@host или Host из ~/.ssh/config. В скрипт IP не зашит.
# Удалённая БД по умолчанию: /opt/vels-claude/data/sessions.db
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${STAND_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
DUMP_DIR="${STAND_DUMP_DIR:-$ROOT/data/dumps}"
REMOTE_DB="${STAND_DUMP_REMOTE_DB:-/opt/vels-claude/data/sessions.db}"
REMOTE_USER="${STAND_DUMP_REMOTE_USER:-vels-bot}"

if [[ "${STAND_DUMP_FETCH:-}" != "1" ]]; then
    cat >&2 <<EOF
Обновление дампа с прода только по явной просьбе пользователя.

Если пользователь попросил снять свежий дамп:
  STAND_DUMP_FETCH=1 STAND_DUMP_SSH=user@host bash scripts/fetch_stand_dump.sh

restore_stand_db.sh / run_stand.sh сами на сервер не ходят.
EOF
    exit 2
fi

if [[ -z "${STAND_DUMP_SSH:-}" ]]; then
    echo "Задайте STAND_DUMP_SSH (user@host или ssh Host из ~/.ssh/config)." >&2
    exit 1
fi

command -v ssh >/dev/null 2>&1 || { echo "Нужен ssh." >&2; exit 1; }
command -v scp >/dev/null 2>&1 || { echo "Нужен scp." >&2; exit 1; }

DATE="$(date +%Y-%m-%d)"
REMOTE_TMP="/tmp/ai-workspace-sessions-${DATE}.db"
LOCAL_NAME="sessions-${DATE}.db"

mkdir -p "$DUMP_DIR"

echo "Снимаю backup SQLite на сервере (сервис не останавливаю)."
# sqlite3 .backup безопасен при живом WAL. Пишем во /tmp, не в data/ на проде.
ssh "$STAND_DUMP_SSH" "sudo -u '$REMOTE_USER' sqlite3 '$REMOTE_DB' \".backup '$REMOTE_TMP'\" && sudo chmod 644 '$REMOTE_TMP'"

scp "$STAND_DUMP_SSH:$REMOTE_TMP" "$DUMP_DIR/$LOCAL_NAME"
(
    cd "$DUMP_DIR"
    ln -sfn "$LOCAL_NAME" sessions.latest.db
)

echo "Дамп сохранён: $DUMP_DIR/$LOCAL_NAME"
echo "Актуальный указатель: $DUMP_DIR/sessions.latest.db"
echo "Дальше: bash scripts/run_stand.sh"
