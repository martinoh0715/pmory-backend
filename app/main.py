from __future__ import annotations

import app.sqlite_patch  # noqa: F401 — must run before Chroma imports

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from mangum import Mangum
from pydantic import BaseModel, Field

from app.config import CHAT_MODEL, CHROMA_DIR, JOBS_REFRESH_TOKEN, PUBLIC_SITE_URL
from app.email.mail import send_welcome_email, verify_unsubscribe_token
from app.email.notify import notify_new_jobs
from app.email.subscribers import deactivate_subscriber, upsert_subscriber
from app.jobs.fetch import list_jobs, refresh_openings
from app.rag.chain import answer_question

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pmory")

app = FastAPI(title="PMory AI Backend", version="2.1.0")

# On Lambda, CORS is handled by the Function URL config only.
# Locally, enable CORS so the static site on another port can call APIs.
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
    notify: dict | None = None


class SubscribeRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    jobAlerts: bool = False


class SubscribeResponse(BaseModel):
    message: str
    email: str
    jobAlerts: bool
    welcomeEmailSent: bool
    warning: str | None = None


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
            "subscribe": "/api/subscribe (POST)",
            "unsubscribe": "/api/unsubscribe (GET)",
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
async def post_jobs_refresh(
    token: str | None = Query(default=None),
    notify: bool = Query(default=True),
):
    """
    Pull latest openings from configured Greenhouse/Lever boards.
    When notify=true (default), email opted-in subscribers about brand-new roles.
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
            jobs_fetch.JOBS_DIR = tmp
            # Keep notify seen-ids writable on Lambda
            from app.email import notify as notify_mod

            notify_mod.SEEN_PATH = tmp / "seen_job_ids.json"

        payload = refresh_openings()
        notify_result = None
        if notify:
            try:
                notify_result = notify_new_jobs(payload.get("jobs") or [])
            except Exception as exc:  # noqa: BLE001
                logger.exception("Notify after refresh failed")
                notify_result = {"error": str(exc)[:300]}
        return JobsResponse(
            updatedAt=payload.get("updatedAt"),
            count=payload.get("count", 0),
            jobs=payload.get("jobs") or [],
            errors=payload.get("errors") or [],
            notify=notify_result,
        )
    except Exception as exc:
        logger.exception("Job refresh failed")
        raise HTTPException(status_code=500, detail=str(exc)[:400]) from exc


@app.post("/api/subscribe", response_model=SubscribeResponse)
async def subscribe(body: SubscribeRequest):
    """
    Save subscriber + send welcome email.
    jobAlerts=false means welcome only; true means also email when new jobs appear.
    """
    try:
        record = upsert_subscriber(str(body.email), body.jobAlerts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Subscribe storage failed")
        detail = f"Could not save subscriber: {exc}"
        raise HTTPException(status_code=500, detail=detail[:400]) from exc

    mail = send_welcome_email(record["email"], bool(body.jobAlerts))
    warning = None
    if not mail.get("ok"):
        err = mail.get("error") or "welcome email not sent"
        warning = err
        # Still a successful subscribe — storage worked; SES may be sandbox-limited
        if "not verified" in err.lower() or "sandbox" in err.lower():
            warning = (
                "Saved your preference, but SES sandbox blocked the welcome email "
                "(recipient must be verified, or request production access)."
            )

    msg = "Subscribed" if record.get("created") else "Subscription updated"
    return SubscribeResponse(
        message=msg,
        email=record["email"],
        jobAlerts=bool(record.get("jobAlerts")),
        welcomeEmailSent=bool(mail.get("ok")),
        warning=warning,
    )


@app.get("/api/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(email: str = Query(...), token: str = Query(...)):
    site = PUBLIC_SITE_URL.rstrip("/")
    if not verify_unsubscribe_token(email, token):
        return HTMLResponse(
            "<h2>Invalid unsubscribe link</h2><p>This link is expired or incorrect.</p>",
            status_code=400,
        )
    deactivate_subscriber(email)
    return HTMLResponse(
        f"""
        <html><body style="font-family:Georgia,serif;padding:2rem">
          <h2>You're unsubscribed</h2>
          <p>{email} will no longer receive PMory job alert emails.</p>
          <p><a href="{site}/#job-alert">Back to PMory</a></p>
        </body></html>
        """
    )


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
