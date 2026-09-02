#!/usr/bin/env bash
# First-time setup on a NEW AWS account: IAM role, ECR, Lambda, Function URL
# Run once, then use scripts/deploy.sh for updates.
set -euo pipefail

# Avoid AWS CLI opening `less` and pausing the script mid-deploy
export AWS_PAGER=""
export PAGER=cat
AWS=(aws --no-cli-pager)

: "${AWS_REGION:=us-east-1}"
: "${LAMBDA_FUNCTION_NAME:=pmory-chat-api}"
: "${ECR_REPOSITORY:=pmory-rag}"
: "${IAM_ROLE_NAME:=pmory-lambda-execution-role}"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY}"
: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

ACCOUNT_ID=$("${AWS[@]}" sts get-caller-identity --query Account --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${IAM_ROLE_NAME}"

echo "==> AWS Account: $ACCOUNT_ID | Region: $AWS_REGION"

# --- IAM role for Lambda ---
if ! "${AWS[@]}" iam get-role --role-name "$IAM_ROLE_NAME" >/dev/null 2>&1; then
  echo "==> Creating IAM role: $IAM_ROLE_NAME"
  "${AWS[@]}" iam create-role \
    --role-name "$IAM_ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": { "Service": "lambda.amazonaws.com" },
        "Action": "sts:AssumeRole"
      }]
    }'
  "${AWS[@]}" iam attach-role-policy \
    --role-name "$IAM_ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
  echo "    Waiting 15s for IAM role propagation..."
  sleep 15
else
  echo "==> IAM role already exists: $IAM_ROLE_NAME"
fi

# --- Build & push image ---
echo "==> Building Docker image (linux/amd64 for Lambda)..."
# Lambda requires Docker V2 manifest — disable BuildKit attestations (OCI index).
docker build --platform linux/amd64 \
  --provenance=false \
  --sbom=false \
  --build-arg OPENAI_API_KEY="$OPENAI_API_KEY" \
  -t "${ECR_REPOSITORY}:${IMAGE_TAG}" .

echo "==> Ensuring ECR repository..."
ECR_DESCRIBE_ERR=$(mktemp)
if "${AWS[@]}" ecr describe-repositories --repository-names "$ECR_REPOSITORY" --region "$AWS_REGION" >/dev/null 2>"$ECR_DESCRIBE_ERR"; then
  echo "    Repository exists: $ECR_REPOSITORY"
elif grep -q RepositoryNotFoundException "$ECR_DESCRIBE_ERR" 2>/dev/null; then
  echo "    Creating repository: $ECR_REPOSITORY"
  if ! "${AWS[@]}" ecr create-repository --repository-name "$ECR_REPOSITORY" --region "$AWS_REGION" --output text --query repository.repositoryName; then
    rm -f "$ECR_DESCRIBE_ERR"
    exit 1
  fi
else
  cat "$ECR_DESCRIBE_ERR" >&2
  rm -f "$ECR_DESCRIBE_ERR"
  echo ""
  echo "=============================================="
  echo "  ECR access blocked for user pmory-deploy"
  echo "=============================================="
  echo ""
  echo "Your IAM user has a permissions boundary that blocks ECR."
  echo "Fix in AWS Console (log in as account root/admin):"
  echo ""
  echo "  1. ECR → Create repository → name: pmory-rag"
  echo "  2. IAM → Users → pmory-deploy → Permissions boundary"
  echo "     → Edit → allow ECR + Lambda (or remove boundary)"
  echo "  3. IAM → Users → pmory-deploy → Add permissions"
  echo "     → AmazonEC2ContainerRegistryPowerUser"
  echo "     → AWSLambda_FullAccess"
  echo ""
  echo "Or run bootstrap once with admin credentials:"
  echo "  aws configure --profile admin    # use root/admin access key"
  echo "  AWS_PROFILE=admin ./scripts/bootstrap-aws.sh"
  echo ""
  echo "Then verify: aws ecr describe-repositories --repository-names pmory-rag"
  echo "=============================================="
  exit 1
fi
rm -f "$ECR_DESCRIBE_ERR"

"${AWS[@]}" ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

docker tag "${ECR_REPOSITORY}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"

ENV_FILE=$(mktemp)
cat > "$ENV_FILE" <<EOF
{
  "Variables": {
    "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
    "OPENAI_API_KEY": "${OPENAI_API_KEY}",
    "CHAT_MODEL": "${CHAT_MODEL:-claude-3-5-sonnet-latest}",
    "CHROMA_PATH": "/var/task/chroma_db"
  }
}
EOF

# --- Lambda function ---
if "${AWS[@]}" lambda get-function --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  echo "==> Lambda exists — updating code and config..."
  "${AWS[@]}" lambda update-function-code \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --image-uri "${ECR_URI}:${IMAGE_TAG}" \
    --region "$AWS_REGION" \
    --output text --query FunctionArn >/dev/null
  "${AWS[@]}" lambda wait function-updated --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"
  "${AWS[@]}" lambda update-function-configuration \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --region "$AWS_REGION" \
    --environment "file://${ENV_FILE}" \
    --timeout 30 \
    --memory-size 1536 \
    --output text --query FunctionArn >/dev/null
  echo "    Lambda updated."
else
  echo "==> Creating Lambda function: $LAMBDA_FUNCTION_NAME"
  "${AWS[@]}" lambda create-function \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --package-type Image \
    --code "ImageUri=${ECR_URI}:${IMAGE_TAG}" \
    --role "$ROLE_ARN" \
    --region "$AWS_REGION" \
    --timeout 30 \
    --memory-size 1536 \
    --environment "file://${ENV_FILE}" \
    --output text --query FunctionArn >/dev/null
  "${AWS[@]}" lambda wait function-active --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"
  echo "    Lambda created."
fi

rm -f "$ENV_FILE"

# --- Function URL (always force public AuthType=NONE + invoke permission) ---
if "${AWS[@]}" lambda get-function-url-config --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  echo "==> Function URL exists — ensuring public access (AuthType NONE)..."
  "${AWS[@]}" lambda update-function-url-config \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --region "$AWS_REGION" \
    --auth-type NONE \
    --cors '{"AllowOrigins":["*"],"AllowMethods":["*"],"AllowHeaders":["*"],"MaxAge":86400}' \
    --output text --query AuthType >/dev/null
else
  echo "==> Creating Function URL (public, CORS open)..."
  "${AWS[@]}" lambda create-function-url-config \
    --function-name "$LAMBDA_FUNCTION_NAME" \
    --region "$AWS_REGION" \
    --auth-type NONE \
    --cors '{"AllowOrigins":["*"],"AllowMethods":["*"],"AllowHeaders":["*"],"MaxAge":86400}' \
    --output text --query FunctionUrl >/dev/null
fi

"${AWS[@]}" lambda remove-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --statement-id FunctionURLAllowPublicAccess 2>/dev/null || true
"${AWS[@]}" lambda add-permission \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --statement-id FunctionURLAllowPublicAccess \
  --action lambda:InvokeFunctionUrl \
  --principal "*" \
  --function-url-auth-type NONE \
  --output text --query Statement >/dev/null
echo "    Public Function URL invoke permission set."

FUNCTION_URL=$("${AWS[@]}" lambda get-function-url-config \
  --function-name "$LAMBDA_FUNCTION_NAME" \
  --region "$AWS_REGION" \
  --query FunctionUrl --output text)

echo ""
echo "=============================================="
echo "  PMory chat API is ready!"
echo "=============================================="
echo ""
echo "Function URL:  ${FUNCTION_URL}"
echo "Chat endpoint: ${FUNCTION_URL}api/chat"
echo ""
echo "Test:"
echo "  curl -X POST '${FUNCTION_URL}api/chat' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"message\":\"What Emory courses for PM?\"}'"
echo ""
echo "Update pmory_website/index.html:"
echo "  const CHAT_API_URL = '${FUNCTION_URL}api/chat';"
echo ""
echo "Future deploys: export LAMBDA_FUNCTION_NAME=${LAMBDA_FUNCTION_NAME} && ./scripts/deploy.sh"
echo "=============================================="
