#!/usr/bin/env bash
# Ensure Lambda Function URL allows public access (fixes 403 Forbidden)
set -euo pipefail

export AWS_PAGER=""
export PAGER=cat
AWS=(aws --no-cli-pager)

: "${AWS_REGION:=us-east-1}"
: "${LAMBDA_FUNCTION_NAME:=pmory-chat-api}"

echo "==> Current Function URL config:"
"${AWS[@]}" lambda get-function-url-config \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --output table

echo ""
echo "==> Forcing AuthType=NONE + open CORS..."
"${AWS[@]}" lambda update-function-url-config \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --auth-type NONE \
  --cors '{"AllowOrigins":["*"],"AllowMethods":["*"],"AllowHeaders":["*"],"MaxAge":86400}' \
  --output text --query AuthType

echo ""
echo "==> Replacing public invoke permission..."
# Remove stale/wrong statement if present, then add a correct one.
"${AWS[@]}" lambda remove-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --statement-id FunctionURLAllowPublicAccess 2>/dev/null \
  && echo "    Removed old FunctionURLAllowPublicAccess" \
  || echo "    No existing FunctionURLAllowPublicAccess to remove"

"${AWS[@]}" lambda add-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --statement-id FunctionURLAllowPublicAccess \
  --action lambda:InvokeFunctionUrl \
  --principal "*" \
  --function-url-auth-type NONE \
  --output text --query Statement >/dev/null
echo "    Added FunctionURLAllowPublicAccess (InvokeFunctionUrl, AuthType NONE)"

echo ""
echo "==> Resource policy (should include FunctionURLAllowPublicAccess):"
"${AWS[@]}" lambda get-policy \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query Policy --output text | python3 -m json.tool 2>/dev/null \
  || "${AWS[@]}" lambda get-policy \
       --function-name "$LAMBDA_FUNCTION_NAME" \
       --region "$AWS_REGION" \
       --query Policy --output text

FUNCTION_URL=$("${AWS[@]}" lambda get-function-url-config \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query FunctionUrl --output text)

echo ""
echo "==> Testing ${FUNCTION_URL}health"
HTTP_CODE=$(curl -s -o /tmp/pmory-health.json -w "%{http_code}" "${FUNCTION_URL}health" || true)
echo "    HTTP $HTTP_CODE"
head -c 400 /tmp/pmory-health.json 2>/dev/null || true
echo ""

if [[ "$HTTP_CODE" == "403" ]]; then
  echo ""
  echo "Still 403. Check in Console:"
  echo "  Lambda → pmory-chat-api → Configuration → Function URL"
  echo "  Auth type must be NONE, and Resource-based policy must allow public invoke."
  exit 1
fi

echo ""
echo "Chat endpoint: ${FUNCTION_URL}api/chat"
echo "Test:"
echo "  curl -X POST '${FUNCTION_URL}api/chat' -H 'Content-Type: application/json' -d '{\"message\":\"What Emory courses for PM?\"}'"
