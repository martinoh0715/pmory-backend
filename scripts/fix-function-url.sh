#!/usr/bin/env bash
# Ensure Lambda Function URL allows public access (fixes 403 Forbidden)
# AuthType NONE requires BOTH InvokeFunctionUrl AND InvokeFunction.
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
echo "==> Replacing public invoke permissions..."
for SID in FunctionURLAllowPublicAccess FunctionURLAllowPublicInvoke; do
  "${AWS[@]}" lambda remove-permission \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --region "$AWS_REGION" \
    --statement-id "$SID" 2>/dev/null \
    && echo "    Removed $SID" \
    || echo "    No existing $SID"
done

# Required for Function URL auth layer
"${AWS[@]}" lambda add-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --statement-id FunctionURLAllowPublicAccess \
  --action lambda:InvokeFunctionUrl \
  --principal "*" \
  --function-url-auth-type NONE \
  --output text --query Statement >/dev/null
echo "    Added FunctionURLAllowPublicAccess (InvokeFunctionUrl)"

# Required for the function to actually run via the URL (AWS docs)
"${AWS[@]}" lambda add-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --statement-id FunctionURLAllowPublicInvoke \
  --action lambda:InvokeFunction \
  --principal "*" \
  --output text --query Statement >/dev/null
echo "    Added FunctionURLAllowPublicInvoke (InvokeFunction)"

echo ""
echo "==> Resource policy:"
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
  echo "Still 403 after both permissions. Check:"
  echo "  aws lambda get-account-setting --name FunctionURLAuthType"
  echo "  If it returns AWS_IAM, run:"
  echo "  aws lambda put-account-setting --name FunctionURLAuthType --value NONE"
  exit 1
fi

echo ""
echo "Chat endpoint: ${FUNCTION_URL}api/chat"
echo "Test:"
echo "  curl -X POST '${FUNCTION_URL}api/chat' -H 'Content-Type: application/json' -d '{\"message\":\"What Emory courses for PM?\"}'"
