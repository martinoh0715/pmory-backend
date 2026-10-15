from __future__ import annotations

"""Persist job openings / seen-ids to S3 when JOBS_S3_BUCKET is set."""

import json
import logging
from typing import Any

from app.config import (
    AWS_REGION,
    JOBS_S3_BUCKET,
    JOBS_S3_OPENINGS_KEY,
    JOBS_S3_SEEN_KEY,
)

logger = logging.getLogger("pmory.jobs.storage")


def s3_enabled() -> bool:
    return bool(JOBS_S3_BUCKET)


def _client():
    import boto3

    return boto3.client("s3", region_name=AWS_REGION)


def _get_json(key: str) -> dict[str, Any] | None:
    if not s3_enabled():
        return None
    try:
        resp = _client().get_object(Bucket=JOBS_S3_BUCKET, Key=key)
        body = resp["Body"].read().decode("utf-8")
        return json.loads(body)
    except Exception as exc:  # noqa: BLE001
        code = ""
        try:
            code = exc.response.get("Error", {}).get("Code", "")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            code = ""
        if code in ("404", "NoSuchKey", "NotFound"):
            return None
        logger.warning("S3 get s3://%s/%s failed: %s", JOBS_S3_BUCKET, key, exc)
        return None


def _put_json(key: str, payload: dict[str, Any]) -> bool:
    if not s3_enabled():
        return False
    try:
        _client().put_object(
            Bucket=JOBS_S3_BUCKET,
            Key=key,
            Body=json.dumps(payload, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("Wrote s3://%s/%s", JOBS_S3_BUCKET, key)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("S3 put s3://%s/%s failed: %s", JOBS_S3_BUCKET, key, exc)
        return False


def load_openings_s3() -> dict[str, Any] | None:
    return _get_json(JOBS_S3_OPENINGS_KEY)


def save_openings_s3(payload: dict[str, Any]) -> bool:
    return _put_json(JOBS_S3_OPENINGS_KEY, payload)


def load_seen_s3() -> set[str] | None:
    data = _get_json(JOBS_S3_SEEN_KEY)
    if data is None:
        return None
    return set(data.get("ids") or [])


def save_seen_s3(ids: set[str]) -> bool:
    trimmed = sorted(ids)[-5000:]
    return _put_json(JOBS_S3_SEEN_KEY, {"ids": trimmed})
