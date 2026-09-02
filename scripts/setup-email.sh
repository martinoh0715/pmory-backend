#!/usr/bin/env bash
# One-time AWS setup for PMory email alerts (DynamoDB + Lambda role permissions)
set -euo pipefail
export AWS_PAGER=""
AWS=(aws --no-cli-pager)

: "${AWS_REGION:=us-east-1}"
: "${SUBSCRIBERS_TABLE:=pmory-subscribers}"
: "${LAMBDA_FUNCTION_NAME:=pmory-chat-api}"
: "${LAMBDA_ROLE_NAME:=pmory-lambda-execution-role}"

echo "==> Creating DynamoDB table ${SUBSCRIBERS_TABLE} (if missing)..."
if ! "${AWS[@]}" dynamodb describe-table --table-name "$SUBSCRIBERS_TABLE" --region "$AWS_REGION" >/dev/null 2>&1; then
  "${AWS[@]}" dynamodb create-table \
    --table-name "$SUBSCRIBERS_TABLE" \
    --attribute-definitions AttributeName=email,AttributeType=S \
    --key-schema AttributeName=email,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "$AWS_REGION" >/dev/null
  echo "    waiting for table..."
  "${AWS[@]}" dynamodb wait table-exists --table-name "$SUBSCRIBERS_TABLE" --region "$AWS_REGION"
else
  echo "    already exists"
fi

ACCOUNT_ID=$("${AWS[@]}" sts get-caller-identity --query Account --output text)
ROLE_ARN=$("${AWS[@]}" lambda get-function-configuration \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query Role --output text)
ROLE_NAME=$(basename "$ROLE_ARN")

echo "==> Attaching SES + DynamoDB inline policy to role ${ROLE_NAME}..."
POLICY=$(mktemp)
cat > "$POLICY" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SesSend",
      "Effect": "Allow",
      "Action": ["ses:SendEmail", "ses:SendRawEmail"],
      "Resource": "*"
    },
    {
      "Sid": "DynamoSubscribers",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Scan",
        "dynamodb:Query",
        "dynamodb:DescribeTable"
      ],
      "Resource": "arn:aws:dynamodb:${AWS_REGION}:${ACCOUNT_ID}:table/${SUBSCRIBERS_TABLE}"
    }
  ]
}
EOF
"${AWS[@]}" iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name pmory-email-alerts \
  --policy-document "file://${POLICY}"
rm -f "$POLICY"

UNSUB_SECRET="${UNSUBSCRIBE_SECRET:-$(openssl rand -hex 24)}"
echo "==> Updating Lambda env (SES_FROM_EMAIL, table, secrets)..."
# Merge with existing env
EXISTING=$("${AWS[@]}" lambda get-function-configuration \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query 'Environment.Variables' --output json)
ENV_FILE=$(mktemp)
python3 - <<PY > "$ENV_FILE"
import json, os
existing = json.loads('''${EXISTING}''') or {}
existing.update({
  "SES_FROM_EMAIL": os.environ.get("SES_FROM_EMAIL", "martinoh0715@gmail.com"),
  "SES_FROM_NAME": "PMory",
  "SUBSCRIBERS_TABLE": "${SUBSCRIBERS_TABLE}",
  "UNSUBSCRIBE_SECRET": "${UNSUB_SECRET}",
  "PUBLIC_SITE_URL": "https://main.d28vavk28l1jfd.amplifyapp.com",
  "AWS_REGION": "${AWS_REGION}",
})
print(json.dumps({"Variables": existing}))
PY
"${AWS[@]}" lambda update-function-configuration \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --environment "file://${ENV_FILE}" >/dev/null
rm -f "$ENV_FILE"

echo "==> Done."
echo "Next: redeploy backend image (./scripts/deploy.sh) so /api/subscribe is live,"
echo "then test:"
echo "  curl -X POST \"\$FUNCTION_URL/api/subscribe\" -H 'Content-Type: application/json' \\"
echo "    -d '{\"email\":\"martinoh0715@gmail.com\",\"jobAlerts\":true}'"
