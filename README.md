# PMory AI Backend (RAG)

Python RAG backend for the PMory AI assistant, built for Emory students exploring Product Management.

**Stack:** FastAPI · LangChain · Chroma · OpenAI embeddings · Claude (Anthropic) · AWS Lambda (Mangum)

## Architecture

```
POST /api/chat
    → Embed question (OpenAI text-embedding-3-small)
    → Retrieve top-k chunks from Chroma
    → Claude generates answer with retrieved context
```

Knowledge lives in `knowledge/*.md` (not hardcoded JS). The vector index is built offline and shipped with the Lambda image.

## Project layout

```
app/
  main.py          # FastAPI routes + Lambda handler
  config.py        # Environment configuration
  prompts.py       # System prompt
  rag/
    ingest.py      # Document loading + index build
    chain.py       # Retrieval + generation chain
knowledge/         # Source documents (markdown)
scripts/
  build_index.py   # Build Chroma index locally or in Docker
chroma_db/         # Generated vector store (gitignored)
legacy/            # Old Node.js Lambda handler
```

## Setup (local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Add OPENAI_API_KEY and ANTHROPIC_API_KEY

python scripts/build_index.py
uvicorn app.main:app --reload --port 8000
```

Test:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What Emory courses should I take for PM?"}'
```

## Deploy to AWS Lambda (container)

See **[DEPLOY.md](./DEPLOY.md)** for the full step-by-step guide (CLI script, GitHub Actions, local Docker test).

Quick deploy:

```bash
export LAMBDA_FUNCTION_NAME=your-lambda-name
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
./scripts/deploy.sh
```

After bootstrap, use the Function URL printed by the script (e.g. `https://….lambda-url.us-east-1.on.aws/api/chat`). Update `pmory_website/index.html` `CHAT_API_URL` to match.

## API contract

`POST /api/chat`

```json
{ "message": "How do I prepare for PM interviews?" }
```

Response (compatible with existing PMory frontend):

```json
{
  "response": "...",
  "knowledge_used": true,
  "rag_results": ["..."],
  "sources": ["interview-prep.md"],
  "ai_model": "claude-sonnet-5",
  "system": "LangChain RAG + Chroma + Claude"
}
```

## Updating knowledge

1. Edit or add markdown files in `knowledge/`
2. Re-run `python scripts/build_index.py`
3. Rebuild and redeploy the Lambda container image

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Build time (+ optional runtime) | Embeddings via `text-embedding-3-small` |
| `ANTHROPIC_API_KEY` | Runtime | Claude chat completions |
| `CHAT_MODEL` | No | Anthropic model ID |
| `CHROMA_PATH` | No | Path to persisted Chroma DB |
| `RETRIEVAL_K` | No | Number of chunks to retrieve (default 4) |
