#!/usr/bin/env bash
# setup-s3-backup.sh — один раз с правами админа AWS (CloudShell или `aws login` на Mac).
#
# SETUP_MODE=instance-profile (default) — IAM role на EC2
# SETUP_MODE=access-key — IAM user + ключи на сервер (DEPLOY_SSH_HOST=AWS)
set -euo pipefail

REGION="${AWS_REGION:-eu-north-1}"
BUCKET="${AI_WORKSPACE_S3_BUCKET:-ifinance-ai-panel-backups-eu-north-1}"
PREFIX="${AI_WORKSPACE_S3_PREFIX:-prod/ai-panel}"
INSTANCE_ID="${AI_WORKSPACE_INSTANCE_ID:-i-0b6e238f6fcb014bb}"
ROLE_NAME="${AI_WORKSPACE_BACKUP_ROLE:-AiPanelBackupRole}"
PROFILE_NAME="${AI_WORKSPACE_BACKUP_PROFILE:-AiPanelBackupProfile}"
BACKUP_USER="${AI_WORKSPACE_BACKUP_IAM_USER:-AiPanelBackupUploader}"
RETENTION_DAYS="${AI_WORKSPACE_S3_RETENTION_DAYS:-90}"
SETUP_MODE="${SETUP_MODE:-instance-profile}"
DEPLOY_SSH_HOST="${DEPLOY_SSH_HOST:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICY_DOC="$(mktemp)"
trap 'rm -f "$POLICY_DOC"' EXIT

sed "s/BUCKET_NAME/${BUCKET}/g; s|PREFIX_PATH|${PREFIX}|g" \
    "$SCRIPT_DIR/ai-workspace-backup-s3-policy.json" >"$POLICY_DOC"

export AWS_DEFAULT_REGION="$REGION"
echo "Region: $REGION Bucket: $BUCKET Mode: $SETUP_MODE"
aws sts get-caller-identity >/dev/null

ensure_bucket() {
    if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
        echo "Bucket $BUCKET already exists"
    else
        if [[ "$REGION" == "us-east-1" ]]; then
            aws s3api create-bucket --bucket "$BUCKET"
        else
            aws s3api create-bucket --bucket "$BUCKET" \
                --create-bucket-configuration "LocationConstraint=${REGION}"
        fi
        echo "Created bucket $BUCKET"
    fi
    aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
    aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
        '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
    aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration "{
  \"Rules\": [{
    \"ID\": \"expire-old-backups\",
    \"Status\": \"Enabled\",
    \"Filter\": {\"Prefix\": \"${PREFIX}/\"},
    \"Expiration\": {\"Days\": ${RETENTION_DAYS}}
  }]
}"
}

ensure_iam_policy_arn() {
    local policy_name="${ROLE_NAME}-S3Policy"
    local arn
    arn="$(aws iam list-policies --scope Local --query "Policies[?PolicyName=='${policy_name}'].Arn | [0]" --output text)"
    if [[ -z "$arn" || "$arn" == "None" ]]; then
        aws iam create-policy --policy-name "$policy_name" \
            --policy-document "file://${POLICY_DOC}" --query Policy.Arn --output text
    else
        aws iam create-policy-version --policy-arn "$arn" \
            --policy-document "file://${POLICY_DOC}" --set-as-default >/dev/null
        printf '%s' "$arn"
    fi
}

setup_instance_profile() {
    local policy_arn="$1"
    if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
        aws iam create-role --role-name "$ROLE_NAME" \
            --assume-role-policy-document "file://${SCRIPT_DIR}/ai-workspace-backup-trust-ec2.json"
    fi
    aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn "$policy_arn" 2>/dev/null || true
    if ! aws iam get-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null 2>&1; then
        aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME"
        aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME"
    else
        aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME" 2>/dev/null || true
    fi
    sleep 10
    aws ec2 associate-iam-instance-profile \
        --instance-id "$INSTANCE_ID" \
        --iam-instance-profile "Name=${PROFILE_NAME}" 2>/dev/null \
        || aws ec2 replace-iam-instance-profile-association \
            --instance-id "$INSTANCE_ID" \
            --iam-instance-profile "Name=${PROFILE_NAME}"
    echo "Instance profile ${PROFILE_NAME} attached to ${INSTANCE_ID}"
}

setup_access_key_user() {
    local policy_arn="$1"
    if ! aws iam get-user --user-name "$BACKUP_USER" >/dev/null 2>&1; then
        aws iam create-user --user-name "$BACKUP_USER"
    fi
    aws iam attach-user-policy --user-name "$BACKUP_USER" --policy-arn "$policy_arn" 2>/dev/null || true
    local key_json access_key secret_key dest remote_tmp
    key_json="$(aws iam create-access-key --user-name "$BACKUP_USER")"
    access_key="$(printf '%s' "$key_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["AccessKey"]["AccessKeyId"])')"
    secret_key="$(printf '%s' "$key_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["AccessKey"]["SecretAccessKey"])')"
    dest="${AI_WORKSPACE_S3_CREDENTIALS_FILE:-/etc/ai-workspace/s3-backup-credentials.env}"
    if [[ -n "$DEPLOY_SSH_HOST" ]]; then
        remote_tmp="/tmp/s3-backup-credentials.env.$$"
        umask 077
        cat >"/tmp/s3-backup-credentials.env.$$" <<EOF
AWS_DEFAULT_REGION=${REGION}
AWS_ACCESS_KEY_ID=${access_key}
AWS_SECRET_ACCESS_KEY=${secret_key}
EOF
        scp -o BatchMode=yes "/tmp/s3-backup-credentials.env.$$" "${DEPLOY_SSH_HOST}:${remote_tmp}"
        ssh -o BatchMode=yes "$DEPLOY_SSH_HOST" "sudo mkdir -p /etc/ai-workspace && sudo install -m 0600 ${remote_tmp} ${dest} && rm -f ${remote_tmp}"
        rm -f "/tmp/s3-backup-credentials.env.$$"
        echo "Installed ${dest} on ${DEPLOY_SSH_HOST}"
        return 0
    fi
    install -d -m 0700 /etc/ai-workspace
    umask 077
    cat >"${dest}.tmp" <<EOF
AWS_DEFAULT_REGION=${REGION}
AWS_ACCESS_KEY_ID=${access_key}
AWS_SECRET_ACCESS_KEY=${secret_key}
EOF
    install -m 0600 -o root -g root "${dest}.tmp" "$dest"
    rm -f "${dest}.tmp"
    echo "Wrote ${dest} for IAM user ${BACKUP_USER}"
}

ensure_bucket
POLICY_ARN="$(ensure_iam_policy_arn)"
case "$SETUP_MODE" in
    instance-profile) setup_instance_profile "$POLICY_ARN" ;;
    access-key) setup_access_key_user "$POLICY_ARN" ;;
    *) echo "Unknown SETUP_MODE: $SETUP_MODE" >&2; exit 1 ;;
esac

echo ""
echo "Done. On the server:"
echo "  sudo systemctl start ai-workspace-db-backup.service"
echo "  aws s3 ls s3://${BUCKET}/${PREFIX}/"
