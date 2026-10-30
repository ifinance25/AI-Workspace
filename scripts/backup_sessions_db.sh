#!/usr/bin/env bash
# backup_sessions_db.sh — согласованная копия SQLite sessions.db (sqlite3 .backup, безопасно при WAL).
# Вызывается systemd: ai-workspace-db-backup.service (timer nightly).
#
# Переменные (EnvironmentFile опционально /etc/default/ai-workspace-db-backup):
#   AI_WORKSPACE_DB                 путь к БД (по умолчанию /opt/ai-workspace/data/sessions.db)
#   AI_WORKSPACE_BACKUP_DIR         каталог бэкапов (по умолчанию /var/backups/ai-workspace/db)
#   AI_WORKSPACE_BACKUP_RETENTION_DAYS  сколько дней хранить (по умолчанию 14)
#   AI_WORKSPACE_SERVICE_USER       пользователь приложения (по умолчанию ai-workspace)
set -euo pipefail

DB="${AI_WORKSPACE_DB:-/opt/ai-workspace/data/sessions.db}"
BACKUP_DIR="${AI_WORKSPACE_BACKUP_DIR:-/var/backups/ai-workspace/db}"
RETENTION="${AI_WORKSPACE_BACKUP_RETENTION_DAYS:-14}"
RUN_USER="${AI_WORKSPACE_SERVICE_USER:-ai-workspace}"

if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "sqlite3 not found" >&2
    exit 1
fi

if [[ ! -f "$DB" ]]; then
    echo "database missing: $DB" >&2
    exit 1
fi

if ! id "$RUN_USER" >/dev/null 2>&1; then
    echo "user missing: $RUN_USER" >&2
    exit 1
fi

install -d -m 0770 -o root -g "$RUN_USER" "$BACKUP_DIR"

DATE="$(date +%Y-%m-%d)"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGET="$BACKUP_DIR/sessions-${DATE}.db"
TMP="$BACKUP_DIR/.sessions-${STAMP}.db.tmp"

# Один файл на календарный день: повторный запуск в тот же день перезаписывает.
sudo -u "$RUN_USER" sqlite3 "$DB" ".backup '$TMP'"
sudo -u "$RUN_USER" sqlite3 "$TMP" "PRAGMA integrity_check;" | grep -qx 'ok' \
    || { rm -f "$TMP"; echo "integrity_check failed" >&2; exit 1; }

mv -f "$TMP" "$TARGET"
chmod 0640 "$TARGET"
chown root:"$RUN_USER" "$TARGET"
ln -sfn "$(basename "$TARGET")" "$BACKUP_DIR/sessions.latest.db"

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'sessions-????-??-??.db' -mtime +"$RETENTION" -delete

echo "backup ok: $TARGET"
