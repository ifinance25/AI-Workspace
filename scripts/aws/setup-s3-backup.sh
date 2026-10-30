#!/usr/bin/env bash
# setup-s3-backup.sh — один раз из AWS CloudShell (регион eu-north-1) с правами админа.
# Создаёт bucket, IAM role + instance profile, вешает профиль на EC2 AI-Panel.
#
#   export AI_WORKSPACE_INSTANCE_ID=i-0b6e238f6fcb014bb   # опционально
#   bash setup-s3-backup.sh
set -euo pipefail

REGION="${AWS_REGION:-eu-north-1}"
BUCKET="${AI_WORKSPACE_S3_BUCKET:-ifinance-ai-panel-backups-eu-north-1}"
PREFIX="${AI_WORKSPACE_S3_PREFIX:-prod/ai-panel}"
INSTANCE_ID="${AI_WORKSPACE_INSTANCE_ID:-i-0b6e238f6fcb014bb}"
ROLE_NAME="${AI_WORKSPACE_BACKUP_ROLE:-AiPanelBackupRole}"
PROFILE_NAME="${AI_WORKSPACE_BACKUP_PROFILE:-AiPanelBackupProfile}"
RETENTION_DAYS="${AI_WORKSPACE_S3_RETENTION_DAYS:-90}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POLICY_DOC="$(mktemp)"
trap 'rm -f "$POLICY_DOC"' EXIT

sed "s/BUCKET_NAME/${BUCKET}/g; s|PREFIX_PATH|${PREFIX}|g" \
    "$SCRIPT_DIR/ai-workspace-backup-s3-policy.json" >"$POLICY_DOC"

echo "Region: $REGION Bucket: $BUCKET Instance: $INSTANCE_ID"

export AWS_DEFAULT_REGION="$REGION"

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

if ! aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
    aws iam create-role --role-name "$ROLE_NAME" \
        --assume-role-policy-document "file://${SCRIPT_DIR}/ai-workspace-backup-trust-ec2.json"
fi

POLICY_NAME="${ROLE_NAME}-S3Policy"
POLICY_ARN="$(aws iam list-policies --scope Local --query "Policies[?PolicyName=='${POLICY_NAME}'].Arn | [0]" --output text)"
if [[ -z "$POLICY_ARN" || "$POLICY_ARN" == "None" ]]; then
    POLICY_ARN="$(aws iam create-policy --policy-name "$POLICY_NAME" \
        --policy-document "file://${POLICY_DOC}" --query Policy.Arn --output text)"
else
    aws iam create-policy-version --policy-arn "$POLICY_ARN" \
        --policy-document "file://${POLICY_DOC}" --set-as-default >/dev/null
fi

aws iam attach-role-policy --role-name "$ROLE_NAME" --policy-arn "$POLICY_ARN" 2>/dev/null || true

if ! aws iam get-instance-profile --instance-profile-name "$PROFILE_NAME" >/dev/null 2>&1; then
    aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME"
    aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME"
else
    aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME" 2>/dev/null || true
fi

# Дождаться видимости профиля
sleep 10
aws ec2 associate-iam-instance-profile \
    --instance-id "$INSTANCE_ID" \
    --iam-instance-profile "Name=${PROFILE_NAME}" 2>/dev/null \
    || aws ec2 replace-iam-instance-profile-association \
        --instance-id "$INSTANCE_ID" \
        --iam-instance-profile "Name=${PROFILE_NAME}"

echo ""
echo "Done. On the server:"
echo "  sudo install -m 0640 scripts/aws/backup.env.example /etc/default/ai-workspace-backup"
echo "  sudo systemctl start ai-workspace-db-backup.service"
echo "  aws s3 ls s3://${BUCKET}/${PREFIX}/"
