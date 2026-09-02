#!/usr/bin/env bash
# Quickly update Lambda env vars without rebuilding the Docker image.
# Usage: export $(grep -v '^#' .env | xargs) && ./scripts/update-lambda-env.sh
set -euo pipefail

export AWS_PAGER=""
export PAGER=cat
AWS=(aws --no-cli-pager)

: "${AWS_REGION:=us-east-1}"
: "${LAMBDA_FUNCTION_NAME:=pmory-chat-api}"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY}"
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY}"

ENV_FILE=$(mktemp)
cat > "$ENV_FILE" <<EOF
{
  "Variables": {
    "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
    "OPENAI_API_KEY": "${OPENAI_API_KEY}",
    "CHAT_MODEL": "${CHAT_MODEL:-claude-sonnet-5}",
    "CHROMA_PATH": "/var/task/chroma_db",
    "ANONYMIZED_TELEMETRY": "false"
  }
}
EOF

echo "==> Updating ${LAMBDA_FUNCTION_NAME} env (model=${CHAT_MODEL:-claude-sonnet-5}, timeout=60s)..."
"${AWS[@]}" lambda update-function-configuration \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --environment "file://${ENV_FILE}" \
  --timeout 60 \
  --memory-size 1536 \
  --output text --query FunctionArn >/dev/null
rm -f "$ENV_FILE"

"${AWS[@]}" lambda wait function-updated --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"
echo "    Done. Keys updated; image code unchanged."
echo "    Test: curl -X POST \"\$(aws lambda get-function-url-config --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION --query FunctionUrl --output text)api/chat\" -H 'Content-Type: application/json' -d '{\"message\":\"hi\"}'"
