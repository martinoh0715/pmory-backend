from __future__ import annotations

"""SES email helpers for welcome + new-job alerts."""

import hashlib
import hmac
import html as html_lib
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

# Brand colors aligned with pmory.org
_PRIMARY = "#4f46e5"
_TEAL = "#0d9488"
_TEXT = "#1e293b"
_MUTED = "#64748b"
_BG = "#f1f5f9"
_CARD = "#ffffff"


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
        logger.warning("SES send failed to %s: %s", to, exc)
        return {"ok": False, "error": str(exc)[:400], "mode": "ses"}


def _esc(value: str) -> str:
    return html_lib.escape(value or "", quote=True)


def _email_shell(*, preheader: str, title: str, body_html: str, cta_label: str, cta_url: str, unsub: str) -> str:
    """Table-based HTML email that works in Gmail/Outlook."""
    site = PUBLIC_SITE_URL.rstrip("/")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_esc(title)}</title>
</head>
<body style="margin:0;padding:0;background:{_BG};">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">
    {_esc(preheader)}
  </div>
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:{_BG};padding:32px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="width:560px;max-width:100%;background:{_CARD};border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;">
          <tr>
            <td style="background:linear-gradient(135deg,{_PRIMARY} 0%,{_TEAL} 100%);padding:28px 32px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.02em;">
                    PMory
                  </td>
                  <td align="right" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:12px;color:rgba(255,255,255,0.85);">
                    Emory PM hub
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:32px 32px 8px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:{_TEXT};">
              <h1 style="margin:0 0 12px;font-size:26px;line-height:1.25;font-weight:700;letter-spacing:-0.02em;color:{_TEXT};">
                {_esc(title)}
              </h1>
              {body_html}
              <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:28px 0 8px;">
                <tr>
                  <td style="border-radius:10px;background:{_PRIMARY};">
                    <a href="{_esc(cta_url)}" style="display:inline-block;padding:14px 22px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;">
                      {_esc(cta_label)}
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 28px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;font-size:12px;line-height:1.6;color:{_MUTED};border-top:1px solid #e2e8f0;">
              You’re receiving this because you subscribed on
              <a href="{_esc(site)}" style="color:{_PRIMARY};text-decoration:none;">{_esc(site.replace('https://',''))}</a>.
              <br/>
              <a href="{_esc(unsub)}" style="color:{_MUTED};text-decoration:underline;">Unsubscribe</a>
              ·
              <a href="{_esc(site)}/#job-alert" style="color:{_MUTED};text-decoration:underline;">Job Alert</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_welcome_email(email: str, job_alerts: bool) -> dict[str, Any]:
    unsub = unsubscribe_url(email)
    site = PUBLIC_SITE_URL.rstrip("/")
    jobs_url = f"{site}/#job-alert"

    if job_alerts:
        preference = (
            "You’re opted in to <strong>new job alerts</strong> — we’ll email you when "
            "fresh PM roles show up on Greenhouse &amp; Lever boards we track."
        )
        text_pref = (
            "You're opted in to new job alerts — we'll email you when fresh PM roles "
            "show up on the boards we track."
        )
        subject = "You're in — welcome to PMory"
        preheader = "Browse live PM openings, and get alerts when new roles appear."
    else:
        preference = (
            "You chose <strong>welcome only</strong> (no new-job emails). "
            "You can subscribe again anytime and check the job-alerts box."
        )
        text_pref = (
            "You chose welcome only (no new-job emails). "
            "Subscribe again anytime and check the job-alerts box."
        )
        subject = "Welcome to PMory"
        preheader = "Your Emory PM hub for openings, skills, and interview prep."

    text = (
        f"Welcome to PMory\n\n"
        f"Thanks for joining — PMory helps Emory students explore product management "
        f"with live job openings, skill guides, and interview prep.\n\n"
        f"{text_pref}\n\n"
        f"Browse openings: {jobs_url}\n"
        f"Home: {site}\n\n"
        f"Unsubscribe: {unsub}\n"
    )

    body_html = f"""
      <p style="margin:0 0 14px;font-size:16px;line-height:1.6;color:{_TEXT};">
        Thanks for joining — PMory helps Emory students explore product management
        with live openings, skill guides, and interview prep.
      </p>
      <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:{_TEXT};">
        {preference}
      </p>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin:18px 0 4px;background:#f8fafc;border-radius:12px;border:1px solid #e2e8f0;">
        <tr>
          <td style="padding:14px 16px;font-size:14px;line-height:1.55;color:{_MUTED};">
            <strong style="color:{_TEXT};">Quick links</strong><br/>
            · Live PM job board<br/>
            · AI assistant for PM questions<br/>
            · Skillsets &amp; interview prep
          </td>
        </tr>
      </table>
    """

    html = _email_shell(
        preheader=preheader,
        title="Welcome to PMory",
        body_html=body_html,
        cta_label="Browse PM openings",
        cta_url=jobs_url,
        unsub=unsub,
    )
    return send_email(to=email, subject=subject, text_body=text, html_body=html)


def send_new_jobs_email(email: str, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    unsub = unsubscribe_url(email)
    site = PUBLIC_SITE_URL.rstrip("/")
    jobs_url = f"{site}/#job-alert"
    n = len(jobs)
    subject = f"PMory: {n} new PM role{'s' if n != 1 else ''} just posted"
    preheader = f"{n} new product role{'s' if n != 1 else ''} matched your alerts."

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
        + f"\nSee all: {jobs_url}\nUnsubscribe: {unsub}\n"
    )

    cards = []
    for job in jobs[:12]:
        title = _esc(job.get("title") or "PM role")
        company = _esc(job.get("company") or "")
        loc = _esc(job.get("location") or "See posting")
        link = _esc(job.get("link") or site)
        cards.append(
            f"""
            <tr>
              <td style="padding:14px 0;border-bottom:1px solid #e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
                <a href="{link}" style="font-size:15px;font-weight:600;color:{_PRIMARY};text-decoration:none;">{title}</a>
                <div style="margin-top:4px;font-size:13px;color:{_MUTED};">{company} · {loc}</div>
              </td>
            </tr>
            """
        )
    overflow = ""
    if n > 12:
        overflow = f"<p style='margin:12px 0 0;font-size:13px;color:{_MUTED};'>…and {n - 12} more on PMory.</p>"

    body_html = f"""
      <p style="margin:0 0 16px;font-size:16px;line-height:1.6;color:{_TEXT};">
        Fresh product roles from the boards we track — tap a title to open the posting.
      </p>
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
        {''.join(cards)}
      </table>
      {overflow}
    """

    html = _email_shell(
        preheader=preheader,
        title=f"{n} new PM role{'s' if n != 1 else ''}",
        body_html=body_html,
        cta_label="View all openings",
        cta_url=jobs_url,
        unsub=unsub,
    )
    return send_email(to=email, subject=subject, text_body=text, html_body=html)
