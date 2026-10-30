#!/usr/bin/env bash
# backup_upload_s3.sh — выгрузка локальных бэкапов в S3 (SSE-S3 по умолчанию).
set -euo pipefail

BUCKET="${AI_WORKSPACE_S3_BUCKET:-}"
PREFIX="${AI_WORKSPACE_S3_PREFIX:-ai-panel}"
SSE="${AI_WORKSPACE_S3_SSE:-AES256}"
DB_BACKUP_DIR="${AI_WORKSPACE_BACKUP_DIR:-/var/backups/ai-workspace/db}"
PROJECTS_BACKUP_DIR="${AI_WORKSPACE_PROJECTS_BACKUP_DIR:-/var/backups/ai-workspace/projects}"
APP_STATE_BACKUP_DIR="${AI_WORKSPACE_APP_BACKUP_DIR:-/var/backups/ai-workspace/app-state}"
HOST="$(hostname -s 2>/dev/null || hostname)"

if [[ -z "$BUCKET" ]]; then
    echo "AI_WORKSPACE_S3_BUCKET not set — skip S3 upload" >&2
    exit 0
fi

if ! command -v aws >/dev/null 2>&1; then
    echo "aws CLI not found" >&2
    exit 1
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "AWS credentials unavailable (IAM instance profile or /etc/ai-workspace/s3-backup-credentials.env)" >&2
    exit 1
fi

DATE="$(date +%Y-%m-%d)"
DEST="s3://${BUCKET}/${PREFIX%/}/${DATE}/"
DB_FILE="$DB_BACKUP_DIR/sessions-${DATE}.db"
PROJECTS_FILE="$PROJECTS_BACKUP_DIR/projects-${DATE}.tar.gz"
APP_STATE_FILE="$APP_STATE_BACKUP_DIR/app-state-${DATE}.tar.gz"

[[ -f "$DB_FILE" ]] || { echo "missing db backup: $DB_FILE" >&2; exit 1; }

upload_one() {
    local src="$1"
    local name="$2"
    aws s3 cp "$src" "${DEST}${name}" \
        --sse "$SSE" \
        --only-show-errors
}

upload_one "$DB_FILE" "sessions.db"

if [[ "${AI_WORKSPACE_BACKUP_PROJECTS:-1}" == "1" && -f "$PROJECTS_FILE" ]]; then
    upload_one "$PROJECTS_FILE" "projects.tar.gz"
fi

if [[ "${AI_WORKSPACE_BACKUP_APP_STATE:-1}" == "1" && -f "$APP_STATE_FILE" ]]; then
    upload_one "$APP_STATE_FILE" "app-state.tar.gz"
fi

MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT
{
    echo '{'
    echo "  \"date\": \"${DATE}\","
    echo "  \"host\": \"${HOST}\","
    echo "  \"uploaded_at\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
    echo "  \"sessions_db_bytes\": $(stat -c%s "$DB_FILE" 2>/dev/null || stat -f%z "$DB_FILE"),"
    if [[ -f "$PROJECTS_FILE" ]]; then
        echo "  \"projects_tar_bytes\": $(stat -c%s "$PROJECTS_FILE" 2>/dev/null || stat -f%z "$PROJECTS_FILE"),"
    fi
    if [[ -f "$APP_STATE_FILE" ]]; then
        echo "  \"app_state_tar_bytes\": $(stat -c%s "$APP_STATE_FILE" 2>/dev/null || stat -f%z "$APP_STATE_FILE"),"
    fi
    echo "  \"prefix\": \"${PREFIX%/}/${DATE}/\""
    echo '}'
} >"$MANIFEST"
aws s3 cp "$MANIFEST" "${DEST}manifest.json" --sse "$SSE" --only-show-errors

echo "s3 upload ok: ${DEST}"
