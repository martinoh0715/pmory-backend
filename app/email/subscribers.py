from __future__ import annotations

"""Subscriber storage: DynamoDB in AWS, JSON file locally as fallback."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import AWS_REGION, SUBSCRIBERS_FILE, SUBSCRIBERS_TABLE

logger = logging.getLogger("pmory.subscribers")

_file_mode: bool | None = None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _ddb():
    import boto3

    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(SUBSCRIBERS_TABLE)


def _use_file_store() -> bool:
    global _file_mode
    if _file_mode is not None:
        return _file_mode
    try:
        import boto3

        client = boto3.client("dynamodb", region_name=AWS_REGION)
        client.describe_table(TableName=SUBSCRIBERS_TABLE)
        _file_mode = False
    except Exception as exc:  # noqa: BLE001
        logger.info("DynamoDB unavailable (%s) — using %s", exc, SUBSCRIBERS_FILE)
        _file_mode = True
    return _file_mode


def _load_file() -> dict[str, Any]:
    if not SUBSCRIBERS_FILE.exists():
        return {"subscribers": {}}
    return json.loads(SUBSCRIBERS_FILE.read_text(encoding="utf-8"))


def _save_file(data: dict[str, Any]) -> None:
    SUBSCRIBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUBSCRIBERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_subscriber(email: str) -> dict[str, Any] | None:
    email = _normalize_email(email)
    if not email:
        return None
    if _use_file_store():
        return _load_file().get("subscribers", {}).get(email)
    resp = _ddb().get_item(Key={"email": email})
    return resp.get("Item")


def upsert_subscriber(email: str, job_alerts: bool) -> dict[str, Any]:
    """Create or update a subscriber. Returns the stored record + created flag."""
    email = _normalize_email(email)
    if not email or "@" not in email:
        raise ValueError("Invalid email")

    existing = get_subscriber(email)
    now = _now()
    item = {
        "email": email,
        "jobAlerts": bool(job_alerts),
        "createdAt": (existing or {}).get("createdAt") or now,
        "updatedAt": now,
        "status": "active",
    }

    if _use_file_store():
        data = _load_file()
        data.setdefault("subscribers", {})[email] = item
        _save_file(data)
    else:
        _ddb().put_item(Item=item)

    return {**item, "created": existing is None, "updated": existing is not None}


def deactivate_subscriber(email: str) -> bool:
    email = _normalize_email(email)
    existing = get_subscriber(email)
    if not existing:
        return False
    existing["status"] = "unsubscribed"
    existing["jobAlerts"] = False
    existing["updatedAt"] = _now()
    if _use_file_store():
        data = _load_file()
        data.setdefault("subscribers", {})[email] = existing
        _save_file(data)
    else:
        _ddb().put_item(Item=existing)
    return True


def list_job_alert_subscribers() -> list[dict[str, Any]]:
    if _use_file_store():
        subs = _load_file().get("subscribers", {}).values()
        return [s for s in subs if s.get("status") == "active" and s.get("jobAlerts")]

    table = _ddb()
    items: list[dict[str, Any]] = []
    scan_kwargs: dict[str, Any] = {
        "FilterExpression": "#s = :active AND jobAlerts = :true",
        "ExpressionAttributeNames": {"#s": "status"},
        "ExpressionAttributeValues": {":active": "active", ":true": True},
    }
    while True:
        resp = table.scan(**scan_kwargs)
        items.extend(resp.get("Items") or [])
        if not resp.get("LastEvaluatedKey"):
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items
