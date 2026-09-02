from __future__ import annotations

from dataclasses import dataclass

from anthropic import Anthropic
from langchain_chroma import Chroma

from app.config import (
    ANTHROPIC_API_KEY,
    CHAT_MODEL,
    CHROMA_DIR,
    MAX_DISTANCE_FOR_KNOWLEDGE,
    RETRIEVAL_K,
)
from app.prompts import SYSTEM_PROMPT
from app.rag.ingest import get_embeddings

_vectorstore: Chroma | None = None


@dataclass
class ChatResult:
    response: str
    knowledge_used: bool
    sources: list[str]
    rag_results: list[str]


def get_vectorstore() -> Chroma:
    global _vectorstore
    if _vectorstore is None:
        if not CHROMA_DIR.exists():
            raise FileNotFoundError(
                f"Vector store not found at {CHROMA_DIR}. Run scripts/build_index.py first."
            )
        _vectorstore = Chroma(
            persist_directory=str(CHROMA_DIR),
            embedding_function=get_embeddings(),
        )
    return _vectorstore


def _format_docs(docs) -> str:
    return "\n\n---\n\n".join(doc.page_content for doc in docs)


def retrieve_with_scores(question: str) -> tuple[list, list[float]]:
    store = get_vectorstore()
    results = store.similarity_search_with_score(question, k=RETRIEVAL_K)
    docs = [doc for doc, _ in results]
    scores = [score for _, score in results]
    return docs, scores


def answer_question(question: str) -> ChatResult:
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY is not configured")

    docs, scores = retrieve_with_scores(question)
    knowledge_used = any(score <= MAX_DISTANCE_FOR_KNOWLEDGE for score in scores) if scores else False
    context = _format_docs(docs) if docs else "No relevant context retrieved."

    sources = sorted({doc.metadata.get("source", "unknown") for doc in docs})
    rag_results = [doc.page_content[:240] + ("..." if len(doc.page_content) > 240 else "") for doc in docs]

    system_text = SYSTEM_PROMPT.replace("{context}", context)

    # Call Anthropic directly — ChatAnthropic always sends temperature, which
    # newer models (e.g. claude-sonnet-5) reject as deprecated.
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model=CHAT_MODEL,
            max_tokens=900,
            system=system_text,
            messages=[{"role": "user", "content": question}],
        )
    except Exception as exc:
        raise RuntimeError(f"LLM call failed ({type(exc).__name__}): {exc}") from exc

    response = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    if not response:
        raise RuntimeError("LLM returned an empty response")

    return ChatResult(
        response=response,
        knowledge_used=knowledge_used,
        sources=sources,
        rag_results=rag_results,
    )
