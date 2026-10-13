"""Local knowledge base: chunk documents, embed them, retrieve by similarity.

Reuses the cache's embedder and index classes, but lives in its own collection
so clearing the chat cache never wipes the stored documents.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Any, Callable, Optional

import httpx
from qdrant_client import QdrantClient

from app.core.cache import InMemoryIndex, OllamaEmbedder, QdrantIndex, VectorIndex
from config import settings

logger = logging.getLogger(__name__)

KNOWLEDGE_POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "llm-pulse-knowledge-base")


def chunk_text(text: str, max_words: int) -> list[str]:
    """Pack blank-line separated paragraphs into chunks of at most max_words.

    A paragraph longer than the budget is split at word boundaries; short
    paragraphs are merged so chunks stay dense.
    """
    chunks: list[str] = []
    current: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        words = paragraph.split()
        for start in range(0, len(words), max_words):
            piece = words[start:start + max_words]
            if current and len(current) + len(piece) > max_words:
                chunks.append(" ".join(current))
                current = []
            current.extend(piece)
            if len(current) >= max_words:
                chunks.append(" ".join(current))
                current = []
    if current:
        chunks.append(" ".join(current))
    return chunks


class KnowledgeStore:
    """Documents in, relevant chunk texts out. An accelerator like the cache:
    if the embedder or index is down, retrieval returns nothing and chat continues."""

    def __init__(
        self,
        embedder: Optional[OllamaEmbedder],
        index_factory: Callable[[], VectorIndex],
        min_similarity: Optional[float] = None,
    ) -> None:
        self.embedder = embedder
        self.index_factory = index_factory
        self.min_similarity = settings.RAG_MIN_SIMILARITY if min_similarity is None else min_similarity
        self._index: Optional[VectorIndex] = None
        self._warned = False

    def _resolve_index(self) -> VectorIndex:
        if self._index is None:
            self._index = self.index_factory()
        return self._index

    def _degrade(self, operation: str, exc: Exception) -> None:
        if self._warned:
            logger.debug("Knowledge base %s skipped (%s)", operation, exc)
            return
        self._warned = True
        logger.warning(
            "Knowledge base %s unavailable (%s). Answering without retrieved context.",
            operation,
            exc,
        )

    def count(self) -> int:
        try:
            return self._resolve_index().count()
        except Exception as exc:
            self._degrade("count", exc)
            return 0

    def describe(self) -> str:
        try:
            return self._resolve_index().describe()
        except Exception as exc:
            self._degrade("describe", exc)
            return "unavailable"

    async def add_document(self, text: str, source: str = "pasted") -> int:
        """Chunk, embed, and store. Returns how many chunks were written."""
        chunks = chunk_text(text, settings.KNOWLEDGE_CHUNK_WORDS)
        if not chunks:
            return 0
        try:
            index = self._resolve_index()
            for position, chunk in enumerate(chunks):
                vector = await asyncio.to_thread(self.embedder.embed, chunk)
                # The query text is part of the key, so re-adding a document
                # updates its chunks instead of duplicating them.
                key = f"{source}:{chunk}"
                await asyncio.to_thread(
                    index.upsert,
                    key,
                    vector,
                    {"text": chunk, "source": source, "chunk_index": position, "stored_at": time.time()},
                )
        except Exception as exc:
            self._degrade("store", exc)
            return 0
        logger.info("Stored %d knowledge chunk(s) from '%s'", len(chunks), source[:40])
        return len(chunks)

    async def search(self, query: str, top_k: Optional[int] = None) -> list[str]:
        """Chunk texts nearest to the query, best first. Empty store: no embed call."""
        if self.count() == 0:
            return []
        limit = top_k or settings.RAG_TOP_K
        try:
            vector = await asyncio.to_thread(self.embedder.embed, query)
            hits = await asyncio.to_thread(
                self._resolve_index().search_many, vector, limit, self.min_similarity
            )
        except Exception as exc:
            self._degrade("search", exc)
            return []
        return [dict(payload)["text"] for _, payload in hits]

    async def clear(self) -> str:
        """Forget every stored document. Returns the backend description."""
        try:
            await asyncio.to_thread(self._resolve_index().clear)
        except Exception as exc:
            self._degrade("clear", exc)
            return "unavailable"
        description = self._index.describe()
        logger.info("Knowledge base cleared via %s", description)
        return description


def build_default_knowledge() -> KnowledgeStore:
    """Ollama embeddings + Qdrant when reachable, otherwise a disk-backed local index."""
    embedder = OllamaEmbedder()

    def index_factory() -> VectorIndex:
        try:
            client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
            client.get_collections()
            return QdrantIndex(client, settings.KNOWLEDGE_COLLECTION)
        except Exception as exc:
            logger.warning(
                "Qdrant unreachable on %s:%s (%s). Knowledge base persisted to %s.",
                settings.QDRANT_HOST,
                settings.QDRANT_PORT,
                exc,
                settings.KNOWLEDGE_FILE_PATH,
            )
            return InMemoryIndex(persist_path=settings.KNOWLEDGE_FILE_PATH)

    return KnowledgeStore(embedder=embedder, index_factory=index_factory)


knowledge_service = build_default_knowledge()
