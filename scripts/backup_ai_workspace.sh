#!/usr/bin/env bash
# backup_ai_workspace.sh — локальные бэкапы (SQLite + проекты) и выгрузка в S3.
# EnvironmentFile: /etc/default/ai-workspace-backup (см. scripts/aws/backup.env.example)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/backup_sessions_db.sh"
if [[ "${AI_WORKSPACE_BACKUP_APP_STATE:-1}" == "1" ]]; then
    "$SCRIPT_DIR/backup_app_state.sh"
fi
if [[ "${AI_WORKSPACE_BACKUP_PROJECTS:-1}" == "1" ]]; then
    "$SCRIPT_DIR/backup_projects.sh"
fi
"$SCRIPT_DIR/backup_upload_s3.sh"

echo "backup pipeline finished"
