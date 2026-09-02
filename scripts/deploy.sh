#!/usr/bin/env bash
# Deploy PMory RAG backend to AWS Lambda (container image)
# Prerequisites: aws cli, docker, OPENAI_API_KEY, ANTHROPIC_API_KEY
set -euo pipefail

export AWS_PAGER=""

: "${AWS_REGION:=us-east-1}"
: "${LAMBDA_FUNCTION_NAME:?Set LAMBDA_FUNCTION_NAME to your existing chat Lambda}"
: "${ECR_REPOSITORY:=pmory-rag}"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY for embedding index build}"
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY for Lambda runtime}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "==> Building Docker image (linux/amd64, embeds Chroma index)..."
docker build --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  --build-arg OPENAI_API_KEY="$OPENAI_API_KEY" \
  -t "${ECR_REPOSITORY}:${IMAGE_TAG}" .

echo "==> Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names "$ECR_REPOSITORY" --region "$AWS_REGION" 2>/dev/null \
  || aws ecr create-repository --repository-name "$ECR_REPOSITORY" --region "$AWS_REGION"

echo "==> Logging in to ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "==> Pushing image..."
docker tag "${ECR_REPOSITORY}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

echo "==> Updating Lambda function..."
aws lambda update-function-code \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --image-uri "${ECR_URI}:${IMAGE_TAG}" \
  --region "$AWS_REGION"

echo "==> Waiting for Lambda update..."
aws lambda wait function-updated --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"

echo "==> Setting environment variables..."
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
aws lambda update-function-configuration \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --environment "file://${ENV_FILE}" \
  --timeout 60 \
  --memory-size 1536
rm -f "$ENV_FILE"

echo "==> Done. Test with:"
FUNCTION_URL=$(aws lambda get-function-url-config --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION" --query FunctionUrl --output text 2>/dev/null || echo "(enable Function URL in console)")
echo "curl -X POST ${FUNCTION_URL}api/chat -H 'Content-Type: application/json' -d '{\"message\":\"What Emory courses for PM?\"}'"
