from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import CHROMA_DIR, EMBEDDING_MODEL, KNOWLEDGE_DIR, OPENAI_API_KEY


def load_knowledge_documents(knowledge_dir: Path | None = None) -> list[Document]:
    root = knowledge_dir or KNOWLEDGE_DIR
    documents: list[Document] = []

    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        category = path.stem
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source": path.name,
                    "category": category,
                },
            )
        )

    if not documents:
        raise FileNotFoundError(f"No markdown files found in {root}")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=120,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    )
    return splitter.split_documents(documents)


def build_vector_store(
    output_dir: Path | None = None,
    knowledge_dir: Path | None = None,
) -> Chroma:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required to build the vector index")

    chunks = load_knowledge_documents(knowledge_dir)
    persist_dir = str(output_dir or CHROMA_DIR)

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)

    # Rebuild from scratch each time ingest runs
    import shutil

    out = Path(persist_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_dir,
    )


def get_embeddings() -> OpenAIEmbeddings:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured")
    return OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=OPENAI_API_KEY)
