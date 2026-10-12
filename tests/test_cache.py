"""
Unit tests for the semantic cache engine: the threshold gate, the query-keyed
upsert, and both index backends (Qdrant and the in-memory fallback).
Runnable via `python -m pytest` from the repo root, fully offline.
"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import asyncio

from qdrant_client import QdrantClient

from app.core.cache import InMemoryIndex, QdrantIndex, SemanticCache

# Deterministic unit vectors: cosine(A, A_CLOSE) = 0.95, cosine(A, B) = 0.0
A = [1.0, 0.0, 0.0]
A_CLOSE = [0.95, 0.3122498999, 0.0]
B = [0.0, 1.0, 0.0]

TABLE = {"alpha": A, "alpha-close": A_CLOSE, "beta": B}


class FakeEmbedder:
    """Maps known phrases to fixed vectors so similarity is deterministic."""

    def embed(self, text):
        return TABLE[text]


def make_cache(index):
    return SemanticCache(embedder=FakeEmbedder(), index_factory=lambda: index, similarity_threshold=0.90)


def indexes():
    return {
        "qdrant": QdrantIndex(QdrantClient(location=":memory:"), "test_cache"),
        "in-memory": InMemoryIndex(),
    }


def test_miss_then_exact_hit():
    for label, index in indexes().items():
        cache = make_cache(index)
        assert asyncio.run(cache.get("alpha")) is None, label
        asyncio.run(cache.set("alpha", "RESP", {"model": "local_slm"}))
        hit = asyncio.run(cache.get("alpha"))
        assert hit is not None, label
        assert hit["response"] == "RESP", label
        assert hit["metadata"]["model"] == "local_slm", label
        assert hit["similarity"] > 0.99, label
    print("[PASS] test_miss_then_exact_hit")


def test_above_threshold_returns_cached():
    for label, index in indexes().items():
        cache = make_cache(index)
        asyncio.run(cache.set("alpha", "RESP"))
        hit = asyncio.run(cache.get("alpha-close"))  # similarity 0.95 > 0.90
        assert hit is not None, label
        assert hit["response"] == "RESP", label
        assert 0.90 < hit["similarity"] < 0.96, label
    print("[PASS] test_above_threshold_returns_cached")


def test_below_threshold_misses():
    for label, index in indexes().items():
        cache = make_cache(index)
        asyncio.run(cache.set("alpha", "RESP"))
        assert asyncio.run(cache.get("beta")) is None, label  # similarity 0.0 < 0.90
    print("[PASS] test_below_threshold_misses")


def test_repeated_query_updates_instead_of_duplicating():
    index = InMemoryIndex()
    cache = make_cache(index)
    asyncio.run(cache.set("alpha", "FIRST"))
    asyncio.run(cache.set("alpha", "SECOND"))
    assert len(index._entries) == 1
    assert asyncio.run(cache.get("alpha"))["response"] == "SECOND"
    print("[PASS] test_repeated_query_updates_instead_of_duplicating")


def test_broken_embedder_degrades_to_miss():
    class BrokenEmbedder:
        def embed(self, text):
            raise RuntimeError("service down")

    cache = SemanticCache(embedder=BrokenEmbedder(), index_factory=lambda: InMemoryIndex())
    assert asyncio.run(cache.get("alpha")) is None
    asyncio.run(cache.set("alpha", "RESP"))  # must not raise
    print("[PASS] test_broken_embedder_degrades_to_miss")


if __name__ == "__main__":
    test_miss_then_exact_hit()
    test_above_threshold_returns_cached()
    test_below_threshold_misses()
    test_repeated_query_updates_instead_of_duplicating()
    test_broken_embedder_degrades_to_miss()
    print("\nALL SEMANTIC CACHE TESTS PASSED!")
