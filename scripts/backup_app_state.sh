#!/usr/bin/env bash
# backup_app_state.sh — архив изменяемых данных приложения (без кода и .venv).
set -euo pipefail

INSTALL_DIR="${AI_WORKSPACE_INSTALL_DIR:-/opt/ai-workspace}"
SERVICE_HOME="${AI_WORKSPACE_SERVICE_HOME:-/var/lib/ai-workspace}"
ARCHIVE_DIR="${AI_WORKSPACE_APP_BACKUP_DIR:-/var/backups/ai-workspace/app-state}"
RETENTION="${AI_WORKSPACE_BACKUP_RETENTION_DAYS:-14}"

install -d -m 0750 -o root -g root "$ARCHIVE_DIR"

DATE="$(date +%Y-%m-%d)"
TARGET="$ARCHIVE_DIR/app-state-${DATE}.tar.gz"
TMP="$ARCHIVE_DIR/.app-state-${DATE}.tar.gz.tmp"

TAR_ARGS=()
[[ -d "${INSTALL_DIR}/data" ]] && TAR_ARGS+=(-C "$INSTALL_DIR" data)
[[ -f "${INSTALL_DIR}/.env" ]] && TAR_ARGS+=(-C "$INSTALL_DIR" .env)
[[ -f "${INSTALL_DIR}/config/config.yaml" ]] && TAR_ARGS+=(-C "${INSTALL_DIR}/config" config.yaml)
[[ -d "$SERVICE_HOME" ]] && TAR_ARGS+=(-C "$(dirname "$SERVICE_HOME")" "$(basename "$SERVICE_HOME")")

if [[ ${#TAR_ARGS[@]} -eq 0 ]]; then
    echo "nothing to archive for app state" >&2
    exit 1
fi

tar "${TAR_ARGS[@]}" -czf "$TMP"
mv -f "$TMP" "$TARGET"
chmod 0640 "$TARGET"
ln -sfn "$(basename "$TARGET")" "$ARCHIVE_DIR/app-state.latest.tar.gz"

find "$ARCHIVE_DIR" -maxdepth 1 -type f -name 'app-state-????-??-??.tar.gz' -mtime +"$RETENTION" -delete

echo "app-state archive ok: $TARGET"
