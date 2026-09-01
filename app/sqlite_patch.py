"""Use bundled SQLite for Chroma on platforms with sqlite3 < 3.35 (e.g. AWS Lambda)."""

from __future__ import annotations


def patch_sqlite() -> None:
    try:
        __import__("pysqlite3")
        import sys

        sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
    except ImportError:
        # Local dev on macOS/Linux usually has a new enough system sqlite3.
        pass


patch_sqlite()
