# Deploy PMory RAG Backend to AWS Lambda

## New AWS account? Start here

Your old Function URL (`6zvr36ftm5...`) is gone with the old account. On a **new account**, run the bootstrap script once:

```bash
cd pmory-backend
cp .env.example .env          # add OPENAI_API_KEY + ANTHROPIC_API_KEY
export $(grep -v '^#' .env | xargs)

aws configure                 # new account access key + secret, region us-east-1

chmod +x scripts/bootstrap-aws.sh
./scripts/bootstrap-aws.sh
```

The script prints your **new Function URL**. Paste it into `pmory_website/index.html`:

```javascript
const CHAT_API_URL = 'https://YOUR-NEW-URL.lambda-url.us-east-1.on.aws/api/chat';
```

**Before running bootstrap**, create an IAM access key:
AWS Console → IAM → Users → your user → Security credentials → Create access key → CLI use.

### IAM permissions for `pmory-deploy`

The deploy user needs ECR, Lambda, and IAM (to create the Lambda execution role). Attach either:

- **Managed policies:** `IAMFullAccess`, `AWSLambda_FullAccess`, `AmazonEC2ContainerRegistryPowerUser`

**or** the minimal custom policy in `scripts/pmory-deploy-iam-policy.json` (Console → IAM → Policies → Create → JSON → paste file → attach to user).

If you see `no permissions boundary allows the ecr:CreateRepository action`, your user has a **permissions boundary** that blocks ECR. An account admin must either:

1. Add ECR permissions to that boundary, or
2. Create the repo manually: **ECR → Create repository** → name `pmory-rag` → then re-run bootstrap

---

## Existing Lambda? Use deploy.sh

If you already ran bootstrap (or have a Lambda function), use `scripts/deploy.sh` to push code updates.

---

## Option A — One-command deploy (recommended)

### 1. Install tools (once)

```bash
# macOS
brew install awscli docker

# Ubuntu
sudo apt install awscli docker.io
```

### 2. Configure AWS

```bash
aws configure
# Enter your AWS Access Key ID, Secret, region: us-east-1
```

### 3. Find your Lambda function name

AWS Console → Lambda → find the function whose Function URL matches the URL above.

Or:

```bash
aws lambda list-functions --region us-east-1 \
  --query "Functions[?contains(FunctionArn, 'pmory')].FunctionName" --output table
```

### 4. Convert Lambda to container (first time only)

If the function is still Node.js zip-based:

1. AWS Console → Lambda → your function → **Code** → **Deploy new image**
2. Or create a new container-based function and point the Function URL to it

Package type must be **Image** for this Dockerfile.

### 5. Deploy

```bash
cd pmory-backend
cp .env.example .env
# Edit .env with your keys

export $(grep -v '^#' .env | xargs)
export LAMBDA_FUNCTION_NAME=your-function-name-here

chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

### 6. Test

```bash
curl -X POST "https://6zvr36ftm5cfajwvxscn73zhzi0txfdo.lambda-url.us-east-1.on.aws/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"What Emory courses should I take for PM?"}'
```

Expected: JSON with `"response"`, `"knowledge_used": true`, and `"sources"` listing markdown files.

---

## Option B — GitHub Actions (auto-deploy on push)

Add these secrets in GitHub → `martinoh0715/pmory-backend` → Settings → Secrets:

| Secret | Value |
|--------|-------|
| `AWS_ACCESS_KEY_ID` | IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | IAM secret |
| `LAMBDA_FUNCTION_NAME` | Your Lambda function name |
| `OPENAI_API_KEY` | OpenAI key (build + runtime) |
| `ANTHROPIC_API_KEY` | Anthropic key |

IAM permissions needed: `ecr:*` (or push/pull), `lambda:UpdateFunctionCode`, `lambda:UpdateFunctionConfiguration`, `lambda:GetFunction`.

Then run **Actions → Deploy Lambda → Run workflow**, or push to `main`.

---

## Option C — Local test before deploy

```bash
cp .env.example .env   # fill in keys
docker compose up --build
```

In another terminal:

```bash
# Lambda RIE listens on 8080 inside container; compose maps to 8000
curl -X POST http://localhost:8000/2015-03-31/functions/function/invocations \
  -H "Content-Type: application/json" \
  -d '{"requestContext":{"http":{"method":"POST","path":"/api/chat"}},"body":"{\"message\":\"Hello\"}"}'
```

Or run natively:

```bash
pip install -r requirements.txt
python scripts/build_index.py
uvicorn app.main:app --reload --port 8000
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message":"What is RICE?"}'
```

---

## Lambda settings checklist

| Setting | Value |
|---------|-------|
| Package type | Container image |
| Memory | 1536 MB (minimum 1024) |
| Timeout | 30 seconds |
| Handler | `app.main.handler` (set by Dockerfile CMD) |
| Env vars | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `CHROMA_PATH=/var/task/chroma_db` |
| Function URL | CORS enabled, auth NONE (same as before) |

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `ecr:CreateRepository` AccessDenied | Attach `AmazonEC2ContainerRegistryPowerUser` or see `scripts/pmory-deploy-iam-policy.json`. If a permissions boundary is set, an admin must allow ECR there too. |
| `Vector store not found` | Rebuild image with `OPENAI_API_KEY` build arg so `build_index.py` runs |
| `model not found` | Set `CHAT_MODEL=claude-3-5-sonnet-latest` on Lambda |
| `unsupported version of sqlite3` during Docker build or Lambda cold start | `pysqlite3-binary` is bundled; rebuild image after pulling latest |
| CORS errors | Function URL CORS should allow `*` (already in FastAPI middleware) |

---

## Updating knowledge

1. Edit files in `knowledge/`
2. Re-run `./scripts/deploy.sh` (rebuilds index inside Docker)

No frontend changes required if the Function URL stays the same.
