from __future__ import annotations

"""Detect newly added openings and email opted-in subscribers."""

import json
import logging
from pathlib import Path
from typing import Any

from app.config import JOBS_DIR
from app.email.mail import send_new_jobs_email
from app.email.subscribers import list_job_alert_subscribers

logger = logging.getLogger("pmory.notify")

SEEN_PATH = JOBS_DIR / "seen_job_ids.json"


def _load_seen() -> set[str]:
    if not SEEN_PATH.exists():
        return set()
    try:
        data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        return set(data.get("ids") or [])
    except Exception:  # noqa: BLE001
        return set()


def _save_seen(ids: set[str]) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Keep file bounded
    trimmed = sorted(ids)[-5000:]
    SEEN_PATH.write_text(json.dumps({"ids": trimmed}, indent=2), encoding="utf-8")


def notify_new_jobs(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compare current openings to previously seen IDs.
    On first run, seed seen IDs without emailing (avoid blasting historical posts).
    """
    current_ids = {str(j.get("id")) for j in jobs if j.get("id")}
    seen = _load_seen()

    if not seen:
        _save_seen(current_ids)
        return {
            "newCount": 0,
            "emailed": 0,
            "skipped": "seeded_seen_ids",
            "errors": [],
        }

    new_ids = current_ids - seen
    new_jobs = [j for j in jobs if str(j.get("id")) in new_ids]
    _save_seen(seen | current_ids)

    if not new_jobs:
        return {"newCount": 0, "emailed": 0, "errors": []}

    subscribers = list_job_alert_subscribers()
    errors: list[str] = []
    emailed = 0
    for sub in subscribers:
        email = sub.get("email")
        if not email:
            continue
        result = send_new_jobs_email(email, new_jobs)
        if result.get("ok"):
            emailed += 1
        else:
            errors.append(f"{email}: {result.get('error')}")

    logger.info(
        "New jobs=%s subscribers=%s emailed=%s errors=%s",
        len(new_jobs),
        len(subscribers),
        emailed,
        len(errors),
    )
    return {
        "newCount": len(new_jobs),
        "subscriberCount": len(subscribers),
        "emailed": emailed,
        "errors": errors[:20],
        "sample": [
            {"id": j.get("id"), "title": j.get("title"), "company": j.get("company")}
            for j in new_jobs[:5]
        ],
    }
