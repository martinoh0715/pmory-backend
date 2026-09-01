#!/usr/bin/env python3
"""Build the Chroma vector index from knowledge/*.md"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/build_index.py` from repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import CHROMA_DIR, KNOWLEDGE_DIR  # noqa: E402
from app.rag.ingest import build_vector_store, load_knowledge_documents  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build PMory Chroma vector index")
    parser.add_argument("--knowledge-dir", type=Path, default=KNOWLEDGE_DIR)
    parser.add_argument("--output", type=Path, default=CHROMA_DIR)
    args = parser.parse_args()

    docs = load_knowledge_documents(args.knowledge_dir)
    print(f"Loaded {len(docs)} chunks from {args.knowledge_dir}")

    store = build_vector_store(output_dir=args.output, knowledge_dir=args.knowledge_dir)
    count = store._collection.count()  # noqa: SLF001 — build verification
    print(f"Built vector store at {args.output} ({count} vectors)")


if __name__ == "__main__":
    main()
