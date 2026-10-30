#!/usr/bin/env bash
# bootstrap-s3-on-server.sh — на EC2 под ubuntu (sudo). Нужен /root/.aws-backup-admin.env с admin AWS ключами.
set -euo pipefail

ADMIN_ENV="/root/.aws-backup-admin.env"
[[ -f "$ADMIN_ENV" ]] || {
    echo "Создайте ${ADMIN_ENV} (0600 root) с AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION=eu-north-1" >&2
    exit 1
}

set -a
# shellcheck disable=SC1090
source "$ADMIN_ENV"
set +a

export SETUP_MODE=access-key
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-eu-north-1}"
bash /opt/ai-workspace/scripts/aws/setup-s3-backup.sh

systemctl daemon-reload
systemctl start ai-workspace-db-backup.service
journalctl -u ai-workspace-db-backup.service -n 15 --no-pager

BUCKET="${AI_WORKSPACE_S3_BUCKET:-ifinance-ai-panel-backups-eu-north-1}"
PREFIX="${AI_WORKSPACE_S3_PREFIX:-prod/ai-panel}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-eu-north-1}" aws s3 ls "s3://${BUCKET}/${PREFIX}/"
