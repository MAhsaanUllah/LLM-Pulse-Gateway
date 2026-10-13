"""
Tests for the local knowledge base: chunking, retrieval, the privacy gate that
keeps retrieved text off cloud routes, and the /documents endpoints. Hermetic:
the embedder is a fixed-vector fake, so no Ollama or Qdrant is needed.
"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import asyncio

import app.api.gateway as gateway_module
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

import main
from app.core.cache import InMemoryIndex, QdrantIndex
from app.core.knowledge import KnowledgeStore, chunk_text
from config import settings

# Deterministic unit vectors: cosine(A, A_CLOSE) = 0.95, cosine(A, B) = 0.0
A = [1.0, 0.0, 0.0]
A_CLOSE = [0.95, 0.3122498999, 0.0]
B = [0.0, 1.0, 0.0]

TABLE = {"alpha chunk": A, "beta chunk": B}

# Complex enough that the router sends it to cloud_fortress, unknown enough that
# the fake embedder lands it next to the stored "alpha chunk" vector.
HARD_PROMPT = "analyze the architecture and refactor this algorithm"


class StubCache:
    """Keeps the chat routes off the live Qdrant/Ollama the real service would touch."""

    def __init__(self):
        self.stored = []

    async def get(self, query):
        return None

    async def set(self, query, response, metadata):
        self.stored.append((query, response, metadata))

    async def clear(self):
        return "in-memory(0 entries)"


class FakeEmbedder:
    """Known phrases map to fixed vectors; unknown queries land near A."""

    def embed(self, text):
        return TABLE.get(text, A_CLOSE)


def make_store(index):
    return KnowledgeStore(embedder=FakeEmbedder(), index_factory=lambda: index)


def indexes():
    return {
        "qdrant": QdrantIndex(QdrantClient(location=":memory:"), "test_knowledge"),
        "in-memory": InMemoryIndex(),
    }


def test_chunks_never_exceed_the_word_budget():
    text = "\n\n".join(" ".join(["word"] * 80) for _ in range(5))
    chunks = chunk_text(text, max_words=120)
    assert len(chunks) >= 3
    assert all(len(chunk.split()) <= 120 for chunk in chunks)
    assert sum(len(chunk.split()) for chunk in chunks) == 400


def test_store_then_retrieve_relevant_chunks_and_skip_unrelated():
    for label, index in indexes().items():
        store = make_store(index)
        stored = asyncio.run(store.add_document("alpha chunk", source="doc1"))
        assert stored == 1, label
        hits = asyncio.run(store.search("something close to alpha"))
        assert hits == ["alpha chunk"], label
        assert asyncio.run(store.search("beta chunk")) == [], label


def test_search_returns_at_most_top_k():
    store = make_store(InMemoryIndex())
    asyncio.run(store.add_document("alpha chunk\n\nalpha chunk two", source="doc"))
    hits = asyncio.run(store.search("anything unknown", top_k=1))
    assert len(hits) == 1


def test_re_storing_a_document_overwrites_instead_of_duplicating():
    store = make_store(InMemoryIndex())
    asyncio.run(store.add_document("alpha chunk", source="doc1"))
    asyncio.run(store.add_document("alpha chunk", source="doc1"))
    assert store._resolve_index().describe() == "in-memory(1 entries)"


def test_empty_store_searches_without_touching_the_embedder():
    class Exploder:
        def embed(self, text):
            raise AssertionError("embedder must not be called on an empty store")

    store = KnowledgeStore(embedder=Exploder(), index_factory=lambda: InMemoryIndex())
    assert asyncio.run(store.search("anything")) == []


def _isolated_store(monkeypatch, embedder=None):
    store = make_store(InMemoryIndex())
    if embedder is not None:
        store.embedder = embedder
    monkeypatch.setattr(gateway_module, "knowledge_service", store)
    monkeypatch.setattr(gateway_module, "cache_service", StubCache())
    return store


class FakeProviders:
    """Stands in for provider_manager on the gateway module; records every message."""

    def __init__(self, captured, content="Answer from context."):
        self.captured = captured
        self.content = content

    async def execute_completion(self, **kwargs):
        self.captured.extend(kwargs["messages"])
        return {
            "content": self.content,
            "status": "success",
            "model_used": "fake-model",
            "provider": "fake-provider",
            "tokens_used": 3,
            "truncated": False,
            "metadata": {},
        }

    async def stream_completion(self, model, messages, byok=None, local_only=False):
        self.captured.extend(messages)
        yield {"kind": "delta", "text": self.content}
        yield {
            "kind": "final",
            "content": self.content,
            "status": "success",
            "model_used": "fake-model",
            "provider": "fake-provider",
            "tokens_used": 3,
            "truncated": False,
            "metadata": {},
        }


def test_documents_endpoint_stores_chunks(monkeypatch):
    store = _isolated_store(monkeypatch, FakeEmbedder())
    response = TestClient(main.app).post(
        "/api/gateway/documents",
        json={"text": "alpha chunk", "source": "handbook"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stored"
    assert body["chunks_stored"] == 1
    assert asyncio.run(store.search("something close to alpha"))


def test_documents_rejects_empty_text(monkeypatch):
    _isolated_store(monkeypatch)
    response = TestClient(main.app).post("/api/gateway/documents", json={"text": "   "})
    assert response.status_code == 422


def test_documents_clear_reports_the_backend(monkeypatch):
    _isolated_store(monkeypatch, FakeEmbedder())
    client = TestClient(main.app)
    client.post("/api/gateway/documents", json={"text": "alpha chunk"})
    response = client.post("/api/gateway/documents/clear")
    assert response.status_code == 200
    assert response.json()["knowledge_backend"].startswith("in-memory(0")


def test_rag_injects_chunks_into_the_local_route(monkeypatch):
    store = _isolated_store(monkeypatch, FakeEmbedder())
    asyncio.run(store.add_document("alpha chunk", source="doc"))
    captured = []
    monkeypatch.setattr(gateway_module, "provider_manager", FakeProviders(captured))
    body = TestClient(main.app).post(
        "/api/gateway/chat",
        json={"prompt": "something close to alpha", "tier": "standard"},
    ).json()
    assert body["rag_used"] is True
    assert body["rag_chunks"] == 1
    user_message = [m for m in captured if m["role"] == "user"][-1]["content"]
    assert "alpha chunk" in user_message
    assert "something close to alpha" in user_message


def test_rag_keeps_document_text_off_cloud_routes(monkeypatch):
    store = _isolated_store(monkeypatch, FakeEmbedder())
    asyncio.run(store.add_document("alpha chunk", source="doc"))
    captured = []
    monkeypatch.setattr(gateway_module, "provider_manager", FakeProviders(captured))
    monkeypatch.setattr(settings, "RAG_ALLOW_CLOUD", False)
    body = TestClient(main.app).post(
        "/api/gateway/chat",
        json={"prompt": HARD_PROMPT, "tier": "premium"},
    ).json()
    assert body["destination"] == "cloud_fortress"
    assert body["rag_used"] is False
    user_message = [m for m in captured if m["role"] == "user"][-1]["content"]
    assert "alpha chunk" not in user_message


def test_rag_allow_cloud_flag_lets_chunks_travel(monkeypatch):
    store = _isolated_store(monkeypatch, FakeEmbedder())
    asyncio.run(store.add_document("alpha chunk", source="doc"))
    captured = []
    monkeypatch.setattr(gateway_module, "provider_manager", FakeProviders(captured))
    monkeypatch.setattr(settings, "RAG_ALLOW_CLOUD", True)
    body = TestClient(main.app).post(
        "/api/gateway/chat",
        json={"prompt": HARD_PROMPT, "tier": "premium"},
    ).json()
    assert body["rag_used"] is True
    user_message = [m for m in captured if m["role"] == "user"][-1]["content"]
    assert "alpha chunk" in user_message


def test_rag_stays_silent_when_the_knowledge_store_is_empty(monkeypatch):
    _isolated_store(monkeypatch)
    captured = []
    monkeypatch.setattr(gateway_module, "provider_manager", FakeProviders(captured))
    body = TestClient(main.app).post(
        "/api/gateway/chat",
        json={"prompt": "something close to alpha", "tier": "standard"},
    ).json()
    assert body["rag_used"] is False
    user_message = [m for m in captured if m["role"] == "user"][-1]["content"]
    assert user_message == "something close to alpha"


def test_stream_route_reports_rag_in_the_done_frame(monkeypatch):
    store = _isolated_store(monkeypatch, FakeEmbedder())
    asyncio.run(store.add_document("alpha chunk", source="doc"))
    captured = []
    monkeypatch.setattr(gateway_module, "provider_manager", FakeProviders(captured))
    response = TestClient(main.app).post(
        "/api/gateway/chat/stream",
        json={"prompt": "something close to alpha", "tier": "standard"},
    )
    assert "alpha chunk" in [m for m in captured if m["role"] == "user"][-1]["content"]
    assert '"rag_used": true' in response.text
