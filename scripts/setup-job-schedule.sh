#!/usr/bin/env bash
# One-time: S3 bucket for openings + daily EventBridge → Lambda refresh
set -euo pipefail
export AWS_PAGER=""
AWS=(aws --no-cli-pager)

: "${AWS_REGION:=us-east-1}"
: "${LAMBDA_FUNCTION_NAME:=pmory-chat-api}"
: "${JOBS_S3_BUCKET:=}"
: "${SCHEDULE_NAME:=pmory-daily-job-refresh}"
# 15:00 UTC daily ≈ 11am ET / 8am PT
: "${SCHEDULE_EXPRESSION:=cron(0 15 * * ? *)}"

ACCOUNT_ID=$("${AWS[@]}" sts get-caller-identity --query Account --output text)
if [[ -z "${JOBS_S3_BUCKET}" ]]; then
  JOBS_S3_BUCKET="pmory-jobs-${ACCOUNT_ID}"
fi

echo "==> Ensuring S3 bucket s3://${JOBS_S3_BUCKET} ..."
if ! "${AWS[@]}" s3api head-bucket --bucket "$JOBS_S3_BUCKET" 2>/dev/null; then
  if [[ "$AWS_REGION" == "us-east-1" ]]; then
    "${AWS[@]}" s3api create-bucket --bucket "$JOBS_S3_BUCKET" --region "$AWS_REGION"
  else
    "${AWS[@]}" s3api create-bucket --bucket "$JOBS_S3_BUCKET" --region "$AWS_REGION" \
      --create-bucket-configuration LocationConstraint="$AWS_REGION"
  fi
  "${AWS[@]}" s3api put-public-access-block --bucket "$JOBS_S3_BUCKET" \
    --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  echo "    created"
else
  echo "    already exists"
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/jobs/openings.json" ]]; then
  echo "==> Uploading current openings.json seed..."
  "${AWS[@]}" s3 cp "$ROOT/jobs/openings.json" "s3://${JOBS_S3_BUCKET}/openings.json"
fi

ROLE_ARN=$("${AWS[@]}" lambda get-function-configuration \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query Role --output text)
ROLE_NAME=$(basename "$ROLE_ARN")
FUNCTION_ARN=$("${AWS[@]}" lambda get-function \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query Configuration.FunctionArn --output text)

echo "==> Attaching S3 read/write policy to role ${ROLE_NAME}..."
POLICY=$(mktemp)
cat > "$POLICY" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "JobsBucket",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::${JOBS_S3_BUCKET}",
        "arn:aws:s3:::${JOBS_S3_BUCKET}/*"
      ]
    }
  ]
}
EOF
"${AWS[@]}" iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name pmory-jobs-s3 \
  --policy-document "file://${POLICY}"
rm -f "$POLICY"

echo "==> Setting JOBS_S3_BUCKET on Lambda..."
EXISTING=$("${AWS[@]}" lambda get-function-configuration \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query 'Environment.Variables' --output json)
ENV_FILE=$(mktemp)
python3 - <<PY > "$ENV_FILE"
import json
existing = json.loads('''${EXISTING}''') or {}
existing["JOBS_S3_BUCKET"] = "${JOBS_S3_BUCKET}"
print(json.dumps({"Variables": existing}))
PY
"${AWS[@]}" lambda update-function-configuration \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --environment "file://${ENV_FILE}" >/dev/null
rm -f "$ENV_FILE"
"${AWS[@]}" lambda wait function-updated --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"

echo "==> Creating EventBridge rule ${SCHEDULE_NAME} (${SCHEDULE_EXPRESSION})..."
RULE_ARN=$("${AWS[@]}" events put-rule \
  --name "$SCHEDULE_NAME" \
  --schedule-expression "$SCHEDULE_EXPRESSION" \
  --state ENABLED \
  --description "Daily PMory Greenhouse/Lever job refresh" \
  --region "$AWS_REGION" \
  --query RuleArn --output text)

"${AWS[@]}" lambda add-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --statement-id "${SCHEDULE_NAME}-invoke" \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "$RULE_ARN" \
  --region "$AWS_REGION" >/dev/null 2>&1 || true

"${AWS[@]}" events put-targets \
  --rule "$SCHEDULE_NAME" \
  --region "$AWS_REGION" \
  --targets "Id"="1","Arn"="${FUNCTION_ARN}","Input"="{\"pmory_action\":\"refresh_jobs\"}" >/dev/null

echo "==> Running one refresh now (seed / verify)..."
"${AWS[@]}" lambda invoke \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"pmory_action":"refresh_jobs"}' \
  /tmp/pmory-refresh-out.json >/dev/null
echo "    result:"
python3 - <<'PY'
import json
print(json.dumps(json.load(open("/tmp/pmory-refresh-out.json")), indent=2)[:800])
PY

echo ""
echo "==> Done."
echo "Bucket: s3://${JOBS_S3_BUCKET}"
echo "Schedule: ${SCHEDULE_EXPRESSION} → ${LAMBDA_FUNCTION_NAME}"
echo "Check later: curl \"\$FUNCTION_URL/api/jobs\" | jq .updatedAt"
echo ""
echo "NOTE: If CreateBucket failed (IAM), create the bucket in console then re-run:"
echo "  export JOBS_S3_BUCKET=${JOBS_S3_BUCKET}"
echo "  ./scripts/setup-job-schedule.sh"
