from __future__ import annotations

from dataclasses import dataclass

from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

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

    # Inject context before building the template so curly braces in retrieved
    # docs cannot break LangChain's {variable} formatting.
    system_text = SYSTEM_PROMPT.replace("{context}", context)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_text),
            ("human", "{question}"),
        ]
    )

    llm = ChatAnthropic(
        model=CHAT_MODEL,
        api_key=ANTHROPIC_API_KEY,
        max_tokens=900,
        temperature=0.3,
    )

    chain = prompt | llm | StrOutputParser()
    try:
        response = chain.invoke({"question": question})
    except Exception as exc:
        # Anthropic/OpenAI SDK errors usually stringify to useful status + message
        raise RuntimeError(f"LLM call failed ({type(exc).__name__}): {exc}") from exc

    return ChatResult(
        response=response,
        knowledge_used=knowledge_used,
        sources=sources,
        rag_results=rag_results,
    )
