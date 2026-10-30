#!/usr/bin/env bash
# install-s3-backup-on-server.sh — выполнить НА СЕРВЕРЕ (ssh AWS), когда есть admin AWS creds в env.
#   export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_DEFAULT_REGION=eu-north-1
#   sudo -E bash install-s3-backup-on-server.sh
set -euo pipefail

ROOT="${AI_WORKSPACE_INSTALL_DIR:-/opt/ai-workspace}"
AWS_DIR="${ROOT}/scripts/aws"

[[ -f "${AWS_DIR}/setup-s3-backup.sh" ]] || { echo "missing ${AWS_DIR}/setup-s3-backup.sh" >&2; exit 1; }

export SETUP_MODE="${SETUP_MODE:-access-key}"
export DEPLOY_SSH_HOST=""

bash "${AWS_DIR}/setup-s3-backup.sh"

CREDS="/etc/ai-workspace/s3-backup-credentials.env"
umask 077
install -d -m 0700 -o root -g root /etc/ai-workspace
if [[ -n "${AWS_ACCESS_KEY_ID:-}" && -n "${AWS_SECRET_ACCESS_KEY:-}" ]]; then
    cat >"${CREDS}.tmp" <<EOF
AWS_DEFAULT_REGION=${AWS_DEFAULT_REGION:-eu-north-1}
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
EOF
    install -m 0600 -o root -g root "${CREDS}.tmp" "$CREDS"
    rm -f "${CREDS}.tmp"
fi

[[ -f /etc/default/ai-workspace-backup ]] || install -m 0640 "${AWS_DIR}/backup.env.example" /etc/default/ai-workspace-backup

systemctl daemon-reload
systemctl start ai-workspace-db-backup.service
systemctl status ai-workspace-db-backup.service --no-pager | tail -8

BUCKET="${AI_WORKSPACE_S3_BUCKET:-ifinance-ai-panel-backups-eu-north-1}"
PREFIX="${AI_WORKSPACE_S3_PREFIX:-prod/ai-panel}"
aws s3 ls "s3://${BUCKET}/${PREFIX}/" | tail -5
