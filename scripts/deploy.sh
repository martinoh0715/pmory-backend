#!/usr/bin/env bash
# Deploy PMory RAG backend to AWS Lambda (container image)
# Prerequisites: aws cli, docker, OPENAI_API_KEY, ANTHROPIC_API_KEY
set -euo pipefail

export AWS_PAGER=""
export PAGER=cat
AWS=(aws --no-cli-pager)

: "${AWS_REGION:=us-east-1}"
: "${LAMBDA_FUNCTION_NAME:?Set LAMBDA_FUNCTION_NAME to your existing chat Lambda}"
: "${ECR_REPOSITORY:=pmory-rag}"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY for embedding index build}"
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY for Lambda runtime}"

ACCOUNT_ID=$("${AWS[@]}" sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "==> Building Docker image (linux/amd64, embeds Chroma index)..."
docker build --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  --build-arg OPENAI_API_KEY="$OPENAI_API_KEY" \
  -t "${ECR_REPOSITORY}:${IMAGE_TAG}" .

echo "==> Ensuring ECR repository exists..."
"${AWS[@]}" ecr describe-repositories --repository-names "$ECR_REPOSITORY" --region "$AWS_REGION" >/dev/null 2>&1 \
  || "${AWS[@]}" ecr create-repository --repository-name "$ECR_REPOSITORY" --region "$AWS_REGION" \
       --output text --query repository.repositoryName >/dev/null

echo "==> Logging in to ECR..."
"${AWS[@]}" ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "==> Pushing image..."
docker tag "${ECR_REPOSITORY}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

echo "==> Updating Lambda function..."
"${AWS[@]}" lambda update-function-code \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --image-uri "${ECR_URI}:${IMAGE_TAG}" \
  --region "$AWS_REGION" \
  --output text --query FunctionArn >/dev/null

echo "==> Waiting for Lambda update..."
"${AWS[@]}" lambda wait function-updated --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"

echo "==> Setting environment variables..."
ENV_FILE=$(mktemp)
cat > "$ENV_FILE" <<EOF
{
  "Variables": {
    "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
    "OPENAI_API_KEY": "${OPENAI_API_KEY}",
    "CHAT_MODEL": "${CHAT_MODEL:-claude-sonnet-5}",
    "CHROMA_PATH": "/var/task/chroma_db",
    "ANONYMIZED_TELEMETRY": "false",
    "SES_FROM_EMAIL": "${SES_FROM_EMAIL:-martinoh0715@gmail.com}",
    "SES_FROM_NAME": "${SES_FROM_NAME:-PMory}",
    "SUBSCRIBERS_TABLE": "${SUBSCRIBERS_TABLE:-pmory-subscribers}",
    "UNSUBSCRIBE_SECRET": "${UNSUBSCRIBE_SECRET:-pmory-change-me}",
    "PUBLIC_SITE_URL": "${PUBLIC_SITE_URL:-https://main.d28vavk28l1jfd.amplifyapp.com}"
  }
}
EOF
"${AWS[@]}" lambda update-function-configuration \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --environment "file://${ENV_FILE}" \
  --timeout 60 \
  --memory-size 1536 \
  --output text --query FunctionArn >/dev/null
rm -f "$ENV_FILE"
"${AWS[@]}" lambda wait function-updated --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"

FUNCTION_URL=$("${AWS[@]}" lambda get-function-url-config \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query FunctionUrl --output text 2>/dev/null || echo "(enable Function URL in console)")

if [[ -n "${FUNCTION_URL}" && "${FUNCTION_URL}" != "(enable Function URL in console)" ]]; then
  EXISTING=$("${AWS[@]}" lambda get-function-configuration \
    --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION" \
    --query 'Environment.Variables' --output json)
  ENV_FILE=$(mktemp)
  python3 - <<PY > "$ENV_FILE"
import json
existing = json.loads('''${EXISTING}''') or {}
existing["PUBLIC_API_URL"] = "${FUNCTION_URL}".rstrip("/")
print(json.dumps({"Variables": existing}))
PY
  "${AWS[@]}" lambda update-function-configuration \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --region "$AWS_REGION" \
    --environment "file://${ENV_FILE}" >/dev/null
  rm -f "$ENV_FILE"
  "${AWS[@]}" lambda wait function-updated --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"
fi

echo "==> Done. Model=${CHAT_MODEL:-claude-sonnet-5}"
echo "Test:"
echo "  curl -X POST '${FUNCTION_URL}api/chat' -H 'Content-Type: application/json' -d '{\"message\":\"What Emory courses for PM?\"}'"
echo "  curl -X POST '${FUNCTION_URL}api/subscribe' -H 'Content-Type: application/json' -d '{\"email\":\"martinoh0715@gmail.com\",\"jobAlerts\":true}'"