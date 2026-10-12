"""
Unit tests for the semantic cache engine: the threshold gate, the query-keyed
upsert, expiry, restart durability, and both index backends (Qdrant and the
in-memory fallback). Runnable via `python -m pytest` from the repo root, fully offline.
"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import asyncio
import time

from qdrant_client import QdrantClient

from app.core.cache import InMemoryIndex, QdrantIndex, SemanticCache
from config import settings

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


def test_storing_an_entry_records_when_it_was_stored():
    """Expiry needs an age on the entry itself, not on the process."""
    index = InMemoryIndex()
    cache = make_cache(index)
    asyncio.run(cache.set("alpha", "RESP"))
    stored_at = index._entries["alpha"][1]["stored_at"]
    assert abs(stored_at - time.time()) < 5
    print("[PASS] test_storing_an_entry_records_when_it_was_stored")


def test_an_entry_older_than_the_ttl_is_a_miss(monkeypatch):
    """A stale answer is not the same answer: models change, and a gateway that caches
    forever serves the wrong thing with total confidence."""
    monkeypatch.setattr(settings, "CACHE_TTL_SECONDS", 60)
    for label, index in indexes().items():
        cache = make_cache(index)
        index.upsert("alpha", A, {"query": "alpha", "response": "STALE", "metadata": {},
                                 "stored_at": time.time() - 120})
        assert asyncio.run(cache.get("alpha")) is None, label
    print("[PASS] test_an_entry_older_than_the_ttl_is_a_miss")


def test_an_entry_inside_the_ttl_still_hits(monkeypatch):
    """The other half of the gate: expiry must not turn the cache into a no-op."""
    monkeypatch.setattr(settings, "CACHE_TTL_SECONDS", 60)
    for label, index in indexes().items():
        cache = make_cache(index)
        asyncio.run(cache.set("alpha", "FRESH"))
        hit = asyncio.run(cache.get("alpha"))
        assert hit is not None, label
        assert hit["response"] == "FRESH", label
    print("[PASS] test_an_entry_inside_the_ttl_still_hits")


def test_a_ttl_of_zero_never_expires(monkeypatch):
    monkeypatch.setattr(settings, "CACHE_TTL_SECONDS", 0)
    index = InMemoryIndex()
    cache = make_cache(index)
    index.upsert("alpha", A, {"query": "alpha", "response": "ANCIENT", "metadata": {},
                              "stored_at": 0.0})
    assert asyncio.run(cache.get("alpha"))["response"] == "ANCIENT"
    print("[PASS] test_a_ttl_of_zero_never_expires")


def test_the_in_memory_index_survives_a_restart(tmp_path):
    """Without Qdrant the cache lives in the process, so a restart used to mean every
    prompt paid for a model call again. The file is what makes it durable."""
    path = str(tmp_path / "semantic_cache.json")
    first = InMemoryIndex(persist_path=path)
    first.upsert("alpha", A, {"query": "alpha", "response": "RESP", "metadata": {"model": "local_slm"},
                              "stored_at": time.time()})
    assert os.path.exists(path)

    second = InMemoryIndex(persist_path=path)
    found = second.search(A_CLOSE, 0.90)
    assert found is not None
    assert found[1]["response"] == "RESP"
    print("[PASS] test_the_in_memory_index_survives_a_restart")


def test_a_corrupt_cache_file_starts_empty_instead_of_crashing(tmp_path):
    path = tmp_path / "semantic_cache.json"
    path.write_text("{ not json", encoding="utf-8")
    index = InMemoryIndex(persist_path=str(path))
    assert index.search(A, 0.90) is None
    index.upsert("alpha", A, {"query": "alpha", "response": "RESP", "metadata": {}})
    assert len(index._entries) == 1
    print("[PASS] test_a_corrupt_cache_file_starts_empty_instead_of_crashing")


def test_clearing_empties_the_index_and_drops_the_file(tmp_path):
    path = str(tmp_path / "semantic_cache.json")
    index = InMemoryIndex(persist_path=path)
    index.upsert("alpha", A, {"query": "alpha", "response": "RESP", "metadata": {}})
    index.clear()
    assert index._entries == {}
    assert not os.path.exists(path)
    assert InMemoryIndex(persist_path=path).search(A, 0.90) is None
    print("[PASS] test_clearing_empties_the_index_and_drops_the_file")


def test_clearing_a_qdrant_index_leaves_nothing_to_hit():
    index = QdrantIndex(QdrantClient(location=":memory:"), "test_clear")
    index.upsert("alpha", A, {"query": "alpha", "response": "RESP", "metadata": {}})
    assert index.search(A, 0.90) is not None
    index.clear()
    assert index.search(A, 0.90) is None
    print("[PASS] test_clearing_a_qdrant_index_leaves_nothing_to_hit")


if __name__ == "__main__":
    test_miss_then_exact_hit()
    test_above_threshold_returns_cached()
    test_below_threshold_misses()
    test_repeated_query_updates_instead_of_duplicating()
    test_broken_embedder_degrades_to_miss()
    print("\nALL SEMANTIC CACHE TESTS PASSED!")
