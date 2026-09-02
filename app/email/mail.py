from __future__ import annotations

"""SES email helpers for welcome + new-job alerts."""

import hashlib
import hmac
import logging
from email.utils import formataddr
from typing import Any
from urllib.parse import urlencode

from app.config import (
    AWS_REGION,
    PUBLIC_API_URL,
    PUBLIC_SITE_URL,
    SES_FROM_EMAIL,
    SES_FROM_NAME,
    UNSUBSCRIBE_SECRET,
)

logger = logging.getLogger("pmory.mail")


def unsubscribe_token(email: str) -> str:
    return hmac.new(
        UNSUBSCRIBE_SECRET.encode(),
        email.strip().lower().encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def verify_unsubscribe_token(email: str, token: str) -> bool:
    expected = unsubscribe_token(email)
    return hmac.compare_digest(expected, (token or "").strip())


def unsubscribe_url(email: str) -> str:
    qs = urlencode({"email": email.strip().lower(), "token": unsubscribe_token(email)})
    base = PUBLIC_API_URL.rstrip("/")
    return f"{base}/api/unsubscribe?{qs}"


def _ses_client():
    import boto3

    return boto3.client("ses", region_name=AWS_REGION)


def send_email(*, to: str, subject: str, text_body: str, html_body: str | None = None) -> dict[str, Any]:
    """Send via SES. In local/dev without AWS creds, logs instead of sending."""
    source = formataddr((SES_FROM_NAME, SES_FROM_EMAIL))
    try:
        client = _ses_client()
        body: dict[str, Any] = {"Text": {"Data": text_body, "Charset": "UTF-8"}}
        if html_body:
            body["Html"] = {"Data": html_body, "Charset": "UTF-8"}
        resp = client.send_email(
            Source=source,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": body,
            },
        )
        return {"ok": True, "messageId": resp.get("MessageId"), "mode": "ses"}
    except Exception as exc:  # noqa: BLE001
        # Sandbox / missing IAM / local: surface clearly for API consumers
        logger.warning("SES send failed to %s: %s", to, exc)
        return {"ok": False, "error": str(exc)[:400], "mode": "ses"}


def send_welcome_email(email: str, job_alerts: bool) -> dict[str, Any]:
    unsub = unsubscribe_url(email)
    site = PUBLIC_SITE_URL.rstrip("/")
    if job_alerts:
        alerts_line = "You opted in to emails when new PM roles are posted."
    else:
        alerts_line = (
            "You did not opt in to new-job emails. "
            "You can subscribe again later and check the job-alerts box."
        )
    subject = "Welcome to PMory job alerts"
    text = (
        f"Thanks for subscribing to PMory.\n\n"
        f"{alerts_line}\n\n"
        f"Browse openings: {site}/#job-alert\n\n"
        f"Unsubscribe: {unsub}\n"
    )
    html = f"""
    <div style="font-family:Georgia,serif;line-height:1.5;color:#111">
      <h2>Welcome to PMory</h2>
      <p>{alerts_line}</p>
      <p><a href="{site}/#job-alert">Browse PM openings</a></p>
      <p style="font-size:12px;color:#666">
        <a href="{unsub}">Unsubscribe</a>
      </p>
    </div>
    """
    return send_email(to=email, subject=subject, text_body=text, html_body=html)


def send_new_jobs_email(email: str, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    unsub = unsubscribe_url(email)
    site = PUBLIC_SITE_URL.rstrip("/")
    n = len(jobs)
    subject = f"PMory: {n} new PM role{'s' if n != 1 else ''}"
    lines = []
    for job in jobs[:25]:
        title = job.get("title") or "PM role"
        company = job.get("company") or ""
        link = job.get("link") or site
        loc = job.get("location") or ""
        lines.append(f"- {title} @ {company} ({loc})\n  {link}")
    more = "" if n <= 25 else f"\n…and {n - 25} more on the site.\n"
    text = (
        f"New PM openings matched your PMory alerts:\n\n"
        + "\n".join(lines)
        + more
        + f"\nSee all: {site}/#job-alert\nUnsubscribe: {unsub}\n"
    )
    items_html = "".join(
        f"<li style='margin:0 0 10px'><a href=\"{job.get('link') or site}\">"
        f"{job.get('title') or 'PM role'}</a>"
        f" — {job.get('company') or ''} · {job.get('location') or ''}</li>"
        for job in jobs[:25]
    )
    html = f"""
    <div style="font-family:Georgia,serif;line-height:1.5;color:#111">
      <h2>{n} new PM role{'s' if n != 1 else ''}</h2>
      <ul>{items_html}</ul>
      <p><a href="{site}/#job-alert">View all on PMory</a></p>
      <p style="font-size:12px;color:#666"><a href="{unsub}">Unsubscribe</a></p>
    </div>
    """
    return send_email(to=email, subject=subject, text_body=text, html_body=html)
