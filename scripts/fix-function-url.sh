#!/usr/bin/env bash
# Ensure Lambda Function URL allows public access (fixes 403 Forbidden)
set -euo pipefail

export AWS_PAGER=""
AWS=(aws --no-cli-pager)

: "${AWS_REGION:=us-east-1}"
: "${LAMBDA_FUNCTION_NAME:=pmory-chat-api}"

echo "==> Checking Function URL config..."
"${AWS[@]}" lambda get-function-url-config \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --output table

echo ""
echo "==> Setting auth type to NONE..."
"${AWS[@]}" lambda update-function-url-config \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --auth-type NONE \
  --cors '{"AllowOrigins":["*"],"AllowMethods":["*"],"AllowHeaders":["*"],"MaxAge":86400}' \
  --output text --query FunctionUrl

echo ""
echo "==> Ensuring public invoke permission..."
if "${AWS[@]}" lambda get-policy --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION" 2>/dev/null \
  | grep -q FunctionURLAllowPublicAccess; then
  echo "    Permission already present."
else
  "${AWS[@]}" lambda add-permission \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --region "$AWS_REGION" \
    --statement-id FunctionURLAllowPublicAccess \
    --action lambda:InvokeFunctionUrl \
    --principal "*" \
    --function-url-auth-type NONE \
    --output text --query Statement
  echo "    Permission added."
fi

FUNCTION_URL=$("${AWS[@]}" lambda get-function-url-config \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query FunctionUrl --output text)

echo ""
echo "==> Testing ${FUNCTION_URL}health"
curl -s "${FUNCTION_URL}health" | head -c 300
echo ""
echo ""
echo "Chat endpoint: ${FUNCTION_URL}api/chat"
