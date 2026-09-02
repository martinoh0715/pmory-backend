from __future__ import annotations

import app.sqlite_patch  # noqa: F401 — must run before Chroma imports

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel, Field

from app.config import CHAT_MODEL, CHROMA_DIR
from app.rag.chain import answer_question

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pmory")

app = FastAPI(title="PMory AI Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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


@app.get("/")
async def root():
    return {
        "message": "PMory AI — LangChain RAG backend",
        "model": CHAT_MODEL,
        "vector_store": str(CHROMA_DIR),
        "endpoints": {"health": "/health", "chat": "/api/chat (POST)"},
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
        # Surface a short provider error so Function URL clients can debug
        # without opening CloudWatch (no secrets — API keys never appear here).
        detail = str(exc).strip() or "Internal server error"
        if len(detail) > 400:
            detail = detail[:400] + "…"
        raise HTTPException(status_code=500, detail=detail) from exc


handler = Mangum(app, lifespan="off")
