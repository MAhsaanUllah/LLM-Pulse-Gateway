"""
The streaming route: an answer should arrive as it is written, while the ledger and
the cache still see one complete result. Runnable via `python -m pytest`.
"""

import json
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest
from fastapi.testclient import TestClient

import app.api.gateway as gateway_module
import main


class SpyCache:
    def __init__(self, hit=None):
        self.hit = hit
        self.stored = []
        self.lookups = 0

    async def get(self, query):
        self.lookups += 1
        return self.hit

    async def set(self, query, response, metadata=None):
        self.stored.append((query, response, metadata))


class StreamingStub:
    """Streams three pieces, then reports what a provider would report at the end."""

    def __init__(self, pieces=("Four ", "apples ", "remain."), result=None):
        self.pieces = pieces
        self.asked = 0
        self.result = result or {
            "model_used": "ollama/gemma4:e2b",
            "provider": "local_slm",
            "status": "success",
            "tokens_used": 96,
            "key_source": None,
            "truncated": False,
        }

    async def stream_completion(self, model, messages, **kwargs):
        self.asked += 1
        for piece in self.pieces:
            yield {"kind": "delta", "text": piece}
        yield {"kind": "final", **self.result}

    async def execute_completion(self, model, messages, **kwargs):  # pragma: no cover
        raise AssertionError("the streaming route must not fall back to a blocking call")


def _events(client, payload):
    """Collect the SSE frames as (event, data) pairs."""
    with client.stream("POST", "/api/gateway/chat/stream", json=payload) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        current, pairs = None, []
        for line in res.iter_lines():
            if line.startswith("event:"):
                current = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                pairs.append((current, json.loads(line.split(":", 1)[1].strip())))
        return pairs


def _wired(cache=None, streamer=None):
    cache = cache or SpyCache()
    streamer = streamer or StreamingStub()
    gateway_module.cache_service = cache
    gateway_module.provider_manager = streamer
    return TestClient(main.app), cache, streamer


def test_the_answer_arrives_in_pieces_and_is_whole_at_the_end():
    client, _, streamer = _wired()
    events = _events(client, {"prompt": "How many apples remain from 7 after eating 2?"})

    deltas = [data["text"] for name, data in events if name == "delta"]
    assert deltas == ["Four ", "apples ", "remain."]
    done = [data for name, data in events if name == "done"]
    assert len(done) == 1
    assert done[0]["response"] == "Four apples remain."
    assert done[0]["tokens_used"] == 96
    assert done[0]["model"] == "ollama/gemma4:e2b"
    assert done[0]["status"] == "success"
    print("[PASS] test_the_answer_arrives_in_pieces_and_is_whole_at_the_end")


def test_the_stream_reports_the_lifecycle_so_the_canvas_still_moves():
    client, _, _ = _wired()
    events = _events(client, {"prompt": "How many apples remain from 7 after eating 2?"})

    signals = [data["event"] for name, data in events if name == "signal"]
    assert signals == ["CACHE_MISS", "ROUTING_SIGNAL", "MODEL_EXECUTION", "EVALUATION", "COMPLETION"]
    print("[PASS] test_the_stream_reports_the_lifecycle_so_the_canvas_still_moves")


def test_a_streamed_answer_is_cached_and_ledgered_once_as_a_whole():
    """Per-piece writes would either never cache or cache a fragment, and the ledger
    would count one request as several."""
    recorded = []

    class SpyLedger:
        def record(self, **kwargs):
            recorded.append(kwargs)

    cache = SpyCache()
    streamer = StreamingStub()
    gateway_module.cache_service = cache
    gateway_module.provider_manager = streamer
    client = TestClient(main.app)
    monkey = pytest.MonkeyPatch()
    monkey.setattr(gateway_module, "usage_ledger", SpyLedger())
    try:
        _events(client, {"prompt": "Which number is larger, 12 or 21?"})
    finally:
        monkey.undo()

    assert [q for q, _, _ in cache.stored] == ["Which number is larger, 12 or 21?"]
    assert cache.stored[0][1] == "Four apples remain."
    assert len(recorded) == 1
    assert recorded[0]["tokens_used"] == 96
    assert recorded[0]["cache_hit"] is False
    print("[PASS] test_a_streamed_answer_is_cached_and_ledgered_once_as_a_whole")


def test_a_cut_off_stream_says_so_and_is_not_cached():
    cache = SpyCache()
    client, cache, _ = _wired(
        cache=cache,
        streamer=StreamingStub(result={
            "model_used": "ollama/gemma4:e2b",
            "provider": "local_slm",
            "status": "success",
            "tokens_used": 256,
            "key_source": None,
            "truncated": True,
        }),
    )
    events = _events(client, {"prompt": "Write about apples"})
    done = [data for name, data in events if name == "done"][0]

    assert done["truncated"] is True
    assert cache.stored == []
    print("[PASS] test_a_cut_off_stream_says_so_and_is_not_cached")


def test_a_cache_hit_needs_no_model_and_still_completes_the_stream():
    cache = SpyCache(hit={
        "response": "Four apples remain.",
        "metadata": {"model": "ollama/gemma4:e2b", "provider": "local_slm"},
        "similarity": 0.97,
    })
    client, cache, streamer = _wired(cache=cache)
    events = _events(client, {"prompt": "How many apples remain from 7 after eating 2?"})

    assert streamer.asked == 0
    assert [name for name, _ in events] == ["signal", "delta", "done"]
    assert [data for name, data in events if name == "done"][0]["status"] == "cached"
    assert [data for name, data in events if name == "delta"][0]["text"] == "Four apples remain."
    print("[PASS] test_a_cache_hit_needs_no_model_and_still_completes_the_stream")


def test_a_conversation_in_progress_skips_the_cache_lookup_on_the_stream_too():
    cache = SpyCache(hit={"response": "stale", "metadata": {}, "similarity": 0.99})
    client, cache, streamer = _wired(cache=cache)
    _events(client, {"prompt": "and in one word?", "history": [{"role": "user", "content": "Explain caching"}]})

    assert cache.lookups == 0
    assert streamer.asked == 1
    print("[PASS] test_a_conversation_in_progress_skips_the_cache_lookup_on_the_stream_too")


def test_the_stream_is_gated_like_every_other_route(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "GATEWAY_TOKEN", "s3cret-token")
    client, _, streamer = _wired()
    refused = client.post("/api/gateway/chat/stream", json={"prompt": "hi"})
    assert refused.status_code == 401
    assert streamer.asked == 0
    print("[PASS] test_the_stream_is_gated_like_every_other_route")


if __name__ == "__main__":
    test_the_answer_arrives_in_pieces_and_is_whole_at_the_end()
    test_the_stream_reports_the_lifecycle_so_the_canvas_still_moves()
    test_a_streamed_answer_is_cached_and_ledgered_once_as_a_whole()
    test_a_cut_off_stream_says_so_and_is_not_cached()
    test_a_cache_hit_needs_no_model_and_still_completes_the_stream()
    test_a_conversation_in_progress_skips_the_cache_lookup_on_the_stream_too()
    print("\nALL STREAMING TESTS PASSED!")
