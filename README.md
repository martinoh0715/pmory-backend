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

1. Build the image with your OpenAI key so embeddings are baked in:

```bash
docker build \
  --build-arg OPENAI_API_KEY=$OPENAI_API_KEY \
  -t pmory-rag .

# Local smoke test
docker run -p 9000:8080 \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  pmory-rag
```

2. Push to ECR and deploy as a Lambda function (Python 3.11 container).
3. Set environment variables on Lambda:
   - `ANTHROPIC_API_KEY` (required at runtime)
   - `OPENAI_API_KEY` (optional at runtime if index pre-built; required at build)
   - `CHAT_MODEL` (optional, default `claude-3-5-sonnet-latest`)
4. Attach a **Function URL** with CORS enabled.
5. Update `pmory_website` to point at the new Function URL if it changes.

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
  "ai_model": "claude-3-5-sonnet-latest",
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
