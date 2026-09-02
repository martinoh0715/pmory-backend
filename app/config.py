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

# Optional shared secret for POST /api/jobs/refresh (?token=...)
JOBS_REFRESH_TOKEN = os.environ.get("JOBS_REFRESH_TOKEN", "")
JOBS_DIR = Path(os.environ.get("JOBS_DIR", BASE_DIR / "jobs"))

# Email alerts (SES + DynamoDB)
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
SES_FROM_EMAIL = os.environ.get("SES_FROM_EMAIL", "martinoh0715@gmail.com")
SES_FROM_NAME = os.environ.get("SES_FROM_NAME", "PMory")
SUBSCRIBERS_TABLE = os.environ.get("SUBSCRIBERS_TABLE", "pmory-subscribers")
UNSUBSCRIBE_SECRET = os.environ.get("UNSUBSCRIBE_SECRET", "pmory-dev-unsubscribe-secret")
PUBLIC_SITE_URL = os.environ.get(
    "PUBLIC_SITE_URL",
    "https://main.d28vavk28l1jfd.amplifyapp.com",
)
PUBLIC_API_URL = os.environ.get(
    "PUBLIC_API_URL",
    "https://cjrhfzkkxxi6qvhwbt7pc2wosm0azgfk.lambda-url.us-east-1.on.aws",
)
# Local JSON fallback when DynamoDB is unavailable (dev only)
SUBSCRIBERS_FILE = Path(os.environ.get("SUBSCRIBERS_FILE", BASE_DIR / "jobs" / "subscribers.json"))
