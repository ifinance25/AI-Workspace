#!/usr/bin/env bash
# finish-s3-backup.sh — с Mac после `aws login` или с кодом из браузера.
#   export AWS_DEFAULT_REGION=eu-north-1
#   bash scripts/aws/finish-s3-backup.sh [authorization-code]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SSH_HOST="${DEPLOY_SSH_HOST:-AWS}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-eu-north-1}"

if [[ -n "${1:-}" ]]; then
    printf '%s\n' "$1" | aws login --remote
fi

aws sts get-caller-identity >/dev/null

export SETUP_MODE=instance-profile
export AI_WORKSPACE_INSTANCE_ID="${AI_WORKSPACE_INSTANCE_ID:-i-0b6e238f6fcb014bb}"
bash "${ROOT}/scripts/aws/setup-s3-backup.sh"

ssh -o BatchMode=yes "$SSH_HOST" 'sudo systemctl daemon-reload && sudo systemctl start ai-workspace-db-backup.service'
sleep 30
ssh -o BatchMode=yes "$SSH_HOST" 'journalctl -u ai-workspace-db-backup.service -n 10 --no-pager; aws s3 ls s3://ifinance-ai-panel-backups-eu-north-1/prod/ai-panel/ --recursive 2>/dev/null | tail -8'

echo "Done. Verify nightly: systemctl list-timers ai-workspace-db-backup.timer"
