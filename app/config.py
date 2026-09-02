import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = Path(os.environ.get("KNOWLEDGE_DIR", BASE_DIR / "knowledge"))
CHROMA_DIR = Path(os.environ.get("CHROMA_PATH", BASE_DIR / "chroma_db"))

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.environ.get("CHAT_MODEL", "claude-sonnet-5")

RETRIEVAL_K = int(os.environ.get("RETRIEVAL_K", "4"))
# Chroma returns L2 distance; lower = more similar. Tune if needed.
MAX_DISTANCE_FOR_KNOWLEDGE = float(os.environ.get("MAX_DISTANCE_FOR_KNOWLEDGE", "1.2"))
