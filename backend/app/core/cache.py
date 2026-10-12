from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
import uuid
from typing import Any, Callable, Optional, Protocol

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import settings

logger = logging.getLogger(__name__)

CACHE_POINT_NAMESPACE = uuid.UUID("6f1e6f66-3f0b-4f0b-9b0a-6f0f0f0f0f0f")


class Embedder(Protocol):
    """Turns a query string into a dense vector."""

    def embed(self, text: str) -> list[float]: ...


class OllamaEmbedder:
    """Embeds through the local Ollama service, so the cache needs no python ML stack."""

    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.EMBEDDING_MODEL

    def embed(self, text: str) -> list[float]:
        res = httpx.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
            timeout=30.0,
        )
        res.raise_for_status()
        vector = res.json().get("embedding") or []
        if not vector:
            raise RuntimeError(f"Ollama embedding model '{self.model}' returned no vector")
        return vector


class VectorIndex(Protocol):
    """Stores embedding -> payload and answers nearest-neighbour lookups."""

    def upsert(self, key: str, vector: list[float], payload: dict[str, Any]) -> None: ...

    def search(self, vector: list[float], threshold: float) -> Optional[tuple[float, dict[str, Any]]]: ...

    def clear(self) -> None: ...

    def describe(self) -> str: ...


class QdrantIndex:
    """Qdrant server index. Cosine similarity over a lazily created collection."""

    def __init__(self, client: QdrantClient, collection_name: str) -> None:
        self.client = client
        self.collection_name = collection_name
        self._ready = False

    def _ensure_collection(self, vector_size: int) -> None:
        if self._ready:
            return
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
        self._ready = True

    def upsert(self, key: str, vector: list[float], payload: dict[str, Any]) -> None:
        self._ensure_collection(len(vector))
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=str(uuid.uuid5(CACHE_POINT_NAMESPACE, key)), vector=vector, payload=payload)],
        )

    def search(self, vector: list[float], threshold: float) -> Optional[tuple[float, dict[str, Any]]]:
        self._ensure_collection(len(vector))
        result = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            limit=1,
            score_threshold=threshold,
            with_payload=True,
        )
        if not result.points:
            return None
        return result.points[0].score, dict(result.points[0].payload or {})

    def clear(self) -> None:
        self.client.delete_collection(self.collection_name)
        self._ready = False

    def describe(self) -> str:
        return f"qdrant:{self.collection_name}"


class InMemoryIndex:
    """Process-local cosine index used when no vector database is reachable.

    Entries are keyed by query text so a repeated question updates its embedding
    instead of growing the store. With a `persist_path` the whole store is rewritten
    as JSON on every save, which is what makes answers survive a restart.
    """

    def __init__(self, max_entries: int = 2000, persist_path: Optional[str] = None) -> None:
        self._entries: dict[str, tuple[list[float], dict[str, Any]]] = {}
        self.max_entries = max_entries
        self.persist_path = persist_path
        self._load()

    def _load(self) -> None:
        if not self.persist_path or not os.path.exists(self.persist_path):
            return
        try:
            with open(self.persist_path, encoding="utf-8") as handle:
                stored = json.load(handle)
            for key, entry in stored.items():
                self._entries[key] = (entry["vector"], entry["payload"])
            logger.info("Recovered %d cache entries from %s", len(self._entries), self.persist_path)
        except Exception as exc:
            # A half-written or hand-edited file must not stop the gateway from serving.
            logger.warning("Ignoring unreadable cache file %s (%s)", self.persist_path, exc)
            self._entries = {}

    def _save(self) -> None:
        if not self.persist_path:
            return
        directory = os.path.dirname(self.persist_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.persist_path, "w", encoding="utf-8") as handle:
            json.dump(
                {key: {"vector": vector, "payload": payload} for key, (vector, payload) in self._entries.items()},
                handle,
            )

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if not na or not nb:
            return 0.0
        return dot / (na * nb)

    # ponytail: rewrites the whole JSON file per stored answer. Cheap up to a few
    # thousand entries; beyond that run Qdrant (docker-compose up) instead.
    def upsert(self, key: str, vector: list[float], payload: dict[str, Any]) -> None:
        self._entries[key] = (list(vector), payload)
        while len(self._entries) > self.max_entries:
            self._entries.pop(next(iter(self._entries)))
        self._save()

    def search(self, vector: list[float], threshold: float) -> Optional[tuple[float, dict[str, Any]]]:
        best: Optional[tuple[float, dict[str, Any]]] = None
        for stored_vector, payload in self._entries.values():
            score = self._cosine(vector, stored_vector)
            if score >= threshold and (best is None or score > best[0]):
                best = (score, payload)
        return best

    def clear(self) -> None:
        self._entries = {}
        if self.persist_path and os.path.exists(self.persist_path):
            os.remove(self.persist_path)

    def describe(self) -> str:
        return f"in-memory({len(self._entries)} entries)"


class SemanticCache:
    """Serves a stored answer when a new query embeds above `similarity_threshold`.

    The cache is an accelerator, not a dependency: if the embedder or the index is
    unavailable, reads miss and writes are skipped so requests still complete
    instead of failing with a 500.
    """

    def __init__(
        self,
        embedder: Embedder,
        index_factory: Callable[[], VectorIndex],
        similarity_threshold: float = settings.CACHE_SIMILARITY_THRESHOLD,
    ) -> None:
        self.embedder = embedder
        self.index_factory = index_factory
        self.similarity_threshold = similarity_threshold
        self._index: Optional[VectorIndex] = None
        self._warned = False

    def _resolve_index(self) -> VectorIndex:
        if self._index is None:
            self._index = self.index_factory()
        return self._index

    def _degrade(self, operation: str, exc: Exception) -> None:
        """Log one warning for the first cache failure, then stay quiet."""
        if self._warned:
            logger.debug("Semantic cache %s skipped (%s)", operation, exc)
            return
        self._warned = True
        logger.warning(
            "Semantic cache %s unavailable (%s). Serving requests without cache acceleration.",
            operation,
            exc,
        )

    async def get(self, query: str) -> Optional[dict[str, Any]]:
        """Return the cached entry when a stored query embedding is above threshold."""
        try:
            vector = await asyncio.to_thread(self.embedder.embed, query)
            found = await asyncio.to_thread(self._resolve_index().search, vector, self.similarity_threshold)
        except Exception as exc:
            self._degrade("lookup", exc)
            return None
        if found is None:
            return None
        score, payload = found
        stored_at = payload.get("stored_at")
        ttl = settings.CACHE_TTL_SECONDS
        if ttl > 0 and stored_at and time.time() - stored_at > ttl:
            logger.info("Cache entry for '%s' is older than %ds; re-asking the model.", query[:40], ttl)
            return None
        logger.info("Cache hit via %s (similarity=%.4f) for: %s", self._index.describe(), score, query[:40])
        return {
            "response": payload["response"],
            "metadata": payload.get("metadata", {}),
            "similarity": score,
        }

    async def set(self, query: str, response: str, metadata: Optional[dict[str, Any]] = None) -> None:
        """Embed and store a query/response pair for future semantic lookups."""
        try:
            vector = await asyncio.to_thread(self.embedder.embed, query)
            await asyncio.to_thread(
                self._resolve_index().upsert,
                query,
                vector,
                {"query": query, "response": response, "metadata": metadata or {}, "stored_at": time.time()},
            )
        except Exception as exc:
            self._degrade("store", exc)
            return
        logger.info("Stored cache entry for: %s", query[:40])

    async def clear(self) -> str:
        """Forget every stored answer. The operator's escape hatch after a bad demo."""
        try:
            await asyncio.to_thread(self._resolve_index().clear)
        except Exception as exc:
            self._degrade("clear", exc)
            return "unavailable"
        description = self._index.describe()
        logger.info("Semantic cache cleared via %s", description)
        return description


def build_default_cache() -> SemanticCache:
    """Ollama embeddings + Qdrant when reachable, otherwise a disk-backed local index."""
    embedder = OllamaEmbedder()
    collection = settings.CACHE_COLLECTION

    def index_factory() -> VectorIndex:
        try:
            client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
            client.get_collections()
            return QdrantIndex(client, collection)
        except Exception as exc:
            logger.warning(
                "Qdrant unreachable on %s:%s (%s). Using a local index persisted to %s.",
                settings.QDRANT_HOST,
                settings.QDRANT_PORT,
                exc,
                settings.CACHE_FILE_PATH,
            )
            return InMemoryIndex(persist_path=settings.CACHE_FILE_PATH)

    return SemanticCache(embedder, index_factory)


cache_service = build_default_cache()
