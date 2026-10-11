from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional, Protocol

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import settings

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Turns a query string into a dense vector."""

    def embed(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedder:
    """Production embedder. Loads the sentence-transformers model on first use."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any = None

    def embed(self, text: str) -> list[float]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        vector = self._model.encode(text, normalize_embeddings=True)
        return vector.tolist()


class SemanticCache:
    """Qdrant-backed semantic cache. A query is served from cache when its nearest
    stored embedding scores above `similarity_threshold` (default > 0.90)."""

    def __init__(
        self,
        client: QdrantClient,
        embedder: Embedder,
        collection_name: str = settings.CACHE_COLLECTION,
        similarity_threshold: float = settings.CACHE_SIMILARITY_THRESHOLD,
        vector_size: int = settings.EMBEDDING_DIM,
    ) -> None:
        self.client = client
        self.embedder = embedder
        self.collection_name = collection_name
        self.similarity_threshold = similarity_threshold
        self.vector_size = vector_size
        self._ready = False

    def _ensure_collection(self) -> None:
        if self._ready:
            return
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )
        self._ready = True

    async def get(self, query: str) -> Optional[dict[str, Any]]:
        """Return the cached entry when a stored query embedding is above threshold."""
        vector = await asyncio.to_thread(self.embedder.embed, query)
        await asyncio.to_thread(self._ensure_collection)
        result = await asyncio.to_thread(
            self.client.query_points,
            collection_name=self.collection_name,
            query=vector,
            limit=1,
            score_threshold=self.similarity_threshold,
            with_payload=True,
        )
        if not result.points:
            return None
        hit = result.points[0]
        logger.info("Cache hit (similarity=%.4f) for: %s", hit.score, query[:40])
        return {
            "response": hit.payload["response"],
            "metadata": hit.payload.get("metadata", {}),
            "similarity": hit.score,
        }

    async def set(self, query: str, response: str, metadata: Optional[dict[str, Any]] = None) -> None:
        """Embed and store a query/response pair for future semantic lookups."""
        vector = await asyncio.to_thread(self.embedder.embed, query)
        await asyncio.to_thread(self._ensure_collection)
        await asyncio.to_thread(
            self.client.upsert,
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={"query": query, "response": response, "metadata": metadata or {}},
                )
            ],
        )
        logger.info("Stored cache entry for: %s", query[:40])


def build_default_cache() -> SemanticCache:
    """Qdrant server client per config + the sentence-transformers embedder."""
    client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    return SemanticCache(client, SentenceTransformerEmbedder(settings.EMBEDDING_MODEL))


cache_service = build_default_cache()
