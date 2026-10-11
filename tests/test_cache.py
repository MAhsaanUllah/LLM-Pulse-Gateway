"""
Unit tests for the Qdrant-backed SemanticCache engine.
Verifies embedding generation, cache miss/hit behaviour, and the > 0.90
similarity threshold gate. Runnable via `python -m pytest` from the repo root.
"""

import os
import sys
import asyncio

# Ensure backend root is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from qdrant_client import QdrantClient
from app.core.cache import SemanticCache

# Deterministic unit vectors: cosine(A, A_CLOSE) = 0.95, cosine(A, B) = 0.0
A = [1.0, 0.0, 0.0]
A_CLOSE = [0.95, 0.3122498999, 0.0]
B = [0.0, 1.0, 0.0]


class FakeEmbedder:
    """Maps known phrases to fixed vectors so similarity is deterministic."""

    def __init__(self, table):
        self.table = table

    def embed(self, text):
        return self.table[text]


def make_cache():
    table = {"alpha": A, "alpha-close": A_CLOSE, "beta": B}
    return SemanticCache(
        client=QdrantClient(location=":memory:"),
        embedder=FakeEmbedder(table),
        collection_name="test_cache",
        similarity_threshold=0.90,
        vector_size=3,
    )


def test_miss_then_exact_hit():
    cache = make_cache()
    assert asyncio.run(cache.get("alpha")) is None
    asyncio.run(cache.set("alpha", "RESP", {"model": "local_slm"}))
    hit = asyncio.run(cache.get("alpha"))
    assert hit["response"] == "RESP"
    assert hit["metadata"]["model"] == "local_slm"
    assert hit["similarity"] > 0.99
    print("[PASS] test_miss_then_exact_hit")


def test_above_threshold_returns_cached():
    cache = make_cache()
    asyncio.run(cache.set("alpha", "RESP"))
    hit = asyncio.run(cache.get("alpha-close"))  # similarity 0.95 > 0.90
    assert hit is not None
    assert hit["response"] == "RESP"
    assert 0.90 < hit["similarity"] < 0.96
    print("[PASS] test_above_threshold_returns_cached")


def test_below_threshold_misses():
    cache = make_cache()
    asyncio.run(cache.set("alpha", "RESP"))
    assert asyncio.run(cache.get("beta")) is None  # similarity 0.0 < 0.90
    print("[PASS] test_below_threshold_misses")


if __name__ == "__main__":
    test_miss_then_exact_hit()
    test_above_threshold_returns_cached()
    test_below_threshold_misses()
    print("\nALL SEMANTIC CACHE TESTS PASSED!")
