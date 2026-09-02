from __future__ import annotations

import app.sqlite_patch  # noqa: F401 — must run before Chroma imports

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from mangum import Mangum
from pydantic import BaseModel, Field

from app.config import CHAT_MODEL, CHROMA_DIR, JOBS_REFRESH_TOKEN
from app.jobs.fetch import list_jobs, refresh_openings
from app.rag.chain import answer_question

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pmory")

app = FastAPI(title="PMory AI Backend", version="2.0.0")

# On Lambda, CORS is handled by the Function URL config only.
# Locally, enable CORS so the static site on another port can call /api/jobs.
if not os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    response: str
    knowledge_used: bool
    rag_results: list[str] = []
    sources: list[str] = []
    ai_model: str
    system: str = "LangChain RAG + Chroma + Claude"


class JobsResponse(BaseModel):
    updatedAt: str | None = None
    count: int
    jobs: list[dict]
    errors: list[str] = []


@app.get("/")
async def root():
    return {
        "message": "PMory AI — LangChain RAG backend",
        "model": CHAT_MODEL,
        "vector_store": str(CHROMA_DIR),
        "endpoints": {
            "health": "/health",
            "chat": "/api/chat (POST)",
            "jobs": "/api/jobs",
            "jobs_refresh": "/api/jobs/refresh (POST)",
        },
    }


@app.get("/health")
async def health():
    store_ready = CHROMA_DIR.exists()
    return {
        "status": "OK" if store_ready else "degraded",
        "message": "RAG pipeline ready" if store_ready else "Vector store missing — run build_index",
        "model": CHAT_MODEL,
        "vector_store_ready": store_ready,
    }


@app.get("/api/jobs", response_model=JobsResponse)
async def get_jobs(status: str | None = "open"):
    """List PM roles synced from Greenhouse / Lever boards."""
    data = list_jobs(status=status if status not in ("", "all", "any") else None)
    return JobsResponse(**data)


@app.post("/api/jobs/refresh", response_model=JobsResponse)
async def post_jobs_refresh(token: str | None = Query(default=None)):
    """
    Pull latest openings from configured Greenhouse/Lever boards.
    On Lambda the image filesystem is read-only — refresh writes to /tmp
    for that instance. Prefer scripts/fetch_jobs.py in CI/deploy so
    openings.json is baked into the image.
    """
    expected = JOBS_REFRESH_TOKEN
    if expected and token != expected:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    try:
        from app.jobs import fetch as jobs_fetch

        if not os.access(jobs_fetch.JOBS_DIR, os.W_OK):
            tmp = Path("/tmp/pmory-jobs")
            tmp.mkdir(parents=True, exist_ok=True)
            jobs_fetch.OPENINGS_PATH = tmp / "openings.json"
        payload = refresh_openings()
        return JobsResponse(
            updatedAt=payload.get("updatedAt"),
            count=payload.get("count", 0),
            jobs=payload.get("jobs") or [],
            errors=payload.get("errors") or [],
        )
    except Exception as exc:
        logger.exception("Job refresh failed")
        raise HTTPException(status_code=500, detail=str(exc)[:400]) from exc


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    try:
        result = answer_question(body.message.strip())
        return ChatResponse(
            response=result.response,
            knowledge_used=result.knowledge_used,
            rag_results=result.rag_results,
            sources=result.sources,
            ai_model=CHAT_MODEL,
        )
    except FileNotFoundError as exc:
        logger.error("Vector store missing: %s", exc)
        raise HTTPException(status_code=503, detail="Knowledge base not initialized") from exc
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Chat failed")
        detail = str(exc).strip() or "Internal server error"
        if len(detail) > 400:
            detail = detail[:400] + "…"
        raise HTTPException(status_code=500, detail=detail) from exc


handler = Mangum(app, lifespan="off")

