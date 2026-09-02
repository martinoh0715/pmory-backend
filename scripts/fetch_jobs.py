#!/usr/bin/env python3
"""Fetch PM openings from Greenhouse / Lever into jobs/openings.json"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.jobs.fetch import refresh_openings  # noqa: E402


def main() -> None:
    payload = refresh_openings()
    print(json.dumps({"count": payload.get("count"), "updatedAt": payload.get("updatedAt"), "errors": payload.get("errors")}, indent=2))
    print(f"Wrote {ROOT / 'jobs' / 'openings.json'}")


if __name__ == "__main__":
    main()
