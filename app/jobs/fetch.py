from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("pmory.jobs")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
JOBS_DIR = BASE_DIR / "jobs"
COMPANIES_PATH = JOBS_DIR / "companies.json"
OPENINGS_PATH = JOBS_DIR / "openings.json"

USER_AGENT = "PMoryJobBot/1.0 (+https://github.com/martinoh0715/pmory-backend)"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_config() -> dict[str, Any]:
    with COMPANIES_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _http_get_json(url: str) -> Any:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _normalize_id(source: str, company: str, external_id: str) -> str:
    raw = f"{source}:{company}:{external_id}".lower()
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _matches_pm(title: str, keywords: list[str], exclude: list[str]) -> bool:
    t = title.lower()
    if any(x in t for x in exclude):
        # still allow if it clearly says product manager
        if "product manager" not in t and "product management" not in t and "apm" not in t:
            return False
    return any(k in t for k in keywords)


def _location_from_greenhouse(job: dict) -> str:
    loc = (job.get("location") or {}).get("name") or ""
    if loc:
        return loc
    offices = job.get("offices") or []
    names = [o.get("name") for o in offices if o.get("name")]
    return ", ".join(names) if names else "See posting"


def fetch_greenhouse(company: str, board: str, keywords: list[str], exclude: list[str]) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
    data = _http_get_json(url)
    jobs = []
    for job in data.get("jobs") or []:
        title = job.get("title") or ""
        if not _matches_pm(title, keywords, exclude):
            continue
        ext_id = str(job.get("id") or job.get("internal_job_id") or title)
        absolute = job.get("absolute_url") or f"https://boards.greenhouse.io/{board}/jobs/{ext_id}"
        jobs.append(
            {
                "id": _normalize_id("greenhouse", company, ext_id),
                "company": company,
                "title": title,
                "location": _location_from_greenhouse(job),
                "link": absolute,
                "status": "open",
                "source": "greenhouse",
                "board": board,
                "postedDate": (job.get("updated_at") or job.get("created_at") or _now_iso())[:10],
            }
        )
    return jobs


def fetch_lever(company: str, board: str, keywords: list[str], exclude: list[str]) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{board}?mode=json"
    data = _http_get_json(url)
    if not isinstance(data, list):
        return []
    jobs = []
    for job in data:
        title = job.get("text") or ""
        if not _matches_pm(title, keywords, exclude):
            continue
        ext_id = str(job.get("id") or title)
        cats = job.get("categories") or {}
        location = cats.get("location") or cats.get("commitment") or "See posting"
        if isinstance(location, list):
            location = ", ".join(location)
        link = job.get("hostedUrl") or job.get("applyUrl") or ""
        created = job.get("createdAt")
        if isinstance(created, (int, float)):
            posted = datetime.fromtimestamp(created / 1000, tz=timezone.utc).date().isoformat()
        else:
            posted = _now_iso()[:10]
        jobs.append(
            {
                "id": _normalize_id("lever", company, ext_id),
                "company": company,
                "title": title,
                "location": location or "See posting",
                "link": link,
                "status": "open",
                "source": "lever",
                "board": board,
                "postedDate": posted,
            }
        )
    return jobs


def refresh_openings() -> dict[str, Any]:
    cfg = load_config()
    keywords = [k.lower() for k in cfg.get("title_keywords") or []]
    exclude = [k.lower() for k in cfg.get("exclude_keywords") or []]
    companies = cfg.get("companies") or []

    collected: list[dict] = []
    errors: list[str] = []

    for company in companies:
        name = company.get("name") or company.get("board")
        source = (company.get("source") or "").lower()
        board = company.get("board")
        if not board:
            continue
        try:
            if source == "greenhouse":
                batch = fetch_greenhouse(name, board, keywords, exclude)
            elif source == "lever":
                batch = fetch_lever(name, board, keywords, exclude)
            else:
                errors.append(f"{name}: unknown source {source}")
                continue
            collected.extend(batch)
            logger.info("Fetched %s: %d PM roles", name, len(batch))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            msg = f"{name} ({source}/{board}): {exc}"
            logger.warning(msg)
            errors.append(msg)

    # Dedupe by id
    by_id = {j["id"]: j for j in collected}
    jobs = sorted(by_id.values(), key=lambda j: (j.get("postedDate") or "", j.get("company") or ""), reverse=True)

    payload = {
        "updatedAt": _now_iso(),
        "count": len(jobs),
        "errors": errors,
        "jobs": jobs,
    }
    OPENINGS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_openings() -> dict[str, Any]:
    if not OPENINGS_PATH.exists():
        return {"updatedAt": None, "count": 0, "errors": [], "jobs": []}
    with OPENINGS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def list_jobs(status: str | None = "open") -> dict[str, Any]:
    data = load_openings()
    jobs = data.get("jobs") or []
    if status:
        jobs = [j for j in jobs if (j.get("status") or "open") == status]
    return {
        "updatedAt": data.get("updatedAt"),
        "count": len(jobs),
        "jobs": jobs,
        "errors": data.get("errors") or [],
    }
