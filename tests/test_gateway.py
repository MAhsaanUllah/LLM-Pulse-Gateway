"""
Integration tests for the gateway POST endpoint and the WebSocket telemetry
streamer. Runs fully offline: the semantic cache and provider are stubbed.
Runnable via `python -m pytest` from the repo root.
"""

import os
import sys

# Ensure backend root is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi.testclient import TestClient

import app.api.gateway as gateway_module
import main


class StubCache:
    def __init__(self, hit=None):
        self.hit = hit
        self.stored = []

    async def get(self, query):
        return self.hit

    async def set(self, query, response, metadata=None):
        self.stored.append((query, response, metadata))


class StubProvider:
    def __init__(self, completion=None):
        self.completion = completion or {
            "content": "[stub] answer that is comfortably longer than twenty characters",
            "model_used": "ollama/qwen3.5:4b",
            "provider": "local_slm",
            "status": "success",
            "tokens_used": 42,
            "metadata": {"attempted": []},
        }

    async def execute_completion(self, model, messages, **kwargs):
        return self.completion


def _client(cache_hit=None, completion=None):
    gateway_module.cache_service = StubCache(hit=cache_hit)
    gateway_module.provider_manager = StubProvider(completion=completion)
    return TestClient(main.app)


def test_gateway_reports_when_the_answer_was_cut_short_by_the_token_budget():
    """A capped answer must never look like a finished one — the caller needs the
    difference between 'the model answered' and 'the model ran out of budget'."""
    client = _client(completion={
        "content": "Semantic caching means",
        "model_used": "ollama/gemma4:e2b",
        "provider": "local_slm",
        "status": "success",
        "tokens_used": 276,
        "truncated": True,
        "metadata": {"attempted": []},
    })
    body = client.post("/api/gateway/chat", json={"prompt": "Explain semantic caching"}).json()

    assert body["truncated"] is True

    print("[PASS] test_gateway_reports_when_the_answer_was_cut_short_by_the_token_budget")


def test_a_cut_off_answer_is_never_stored_in_the_cache():
    """The semantic cache replays stored answers for near-identical prompts, so caching
    a truncated reply would serve the same cut-off text forever without re-asking."""
    cache = StubCache()
    gateway_module.cache_service = cache
    gateway_module.provider_manager = StubProvider(completion={
        "content": "Semantic caching means",
        "model_used": "ollama/gemma4:e2b",
        "provider": "local_slm",
        "status": "success",
        "tokens_used": 276,
        "truncated": True,
        "metadata": {"attempted": []},
    })

    TestClient(main.app).post("/api/gateway/chat", json={"prompt": "Explain semantic caching"})

    assert cache.stored == []

    print("[PASS] test_a_cut_off_answer_is_never_stored_in_the_cache")


def test_a_stand_in_answer_is_never_stored_in_the_cache():
    """The stand-in text is generated from the prompt, not from a model, so caching it
    would let a later near-identical prompt replay it as if a model had finally answered."""
    cache = StubCache()
    gateway_module.cache_service = cache
    gateway_module.provider_manager = StubProvider(completion={
        "content": "SIMULATED: no model answered",
        "model_used": "ollama/qwen3.5:4b (stand-in)",
        "provider": "none",
        "status": "simulated",
        "tokens_used": 0,
        "metadata": {"attempted": []},
    })

    body = TestClient(main.app).post("/api/gateway/chat", json={"prompt": "Hello there"}).json()

    assert body["status"] == "simulated"
    assert cache.stored == []

    print("[PASS] test_a_stand_in_answer_is_never_stored_in_the_cache")


def test_gateway_asks_for_plain_bounded_prose():
    """The local model answers in a markdown essay of ~750 tokens, which is both unreadable
    in a chat bubble and over the generated-token budget, so the request must carry the
    shape of the answer it wants."""
    recorded = []

    class RecordingProvider(StubProvider):
        async def execute_completion(self, model, messages, **kwargs):
            recorded.append(messages)
            return self.completion

    gateway_module.cache_service = StubCache()
    gateway_module.provider_manager = RecordingProvider()
    TestClient(main.app).post(
        "/api/gateway/chat", json={"prompt": "how to understand any new language"}
    )

    system = recorded[0][0]
    assert system["role"] == "system"
    assert "markdown" in system["content"].lower()
    assert recorded[0][-1] == {"role": "user", "content": "how to understand any new language"}

    print("[PASS] test_gateway_asks_for_plain_bounded_prose")


def test_gateway_cache_miss_flow():
    client = _client()
    resp = client.post("/api/gateway/chat", json={"prompt": "Hello there"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cache_hit"] is False
    assert body["response"].startswith("[stub]")
    assert body["destination"] == "local_slm"
    assert body["status"] == "success"
    assert body["provider_used"] == "local_slm"
    assert body["tokens_used"] == 42
    print("[PASS] test_gateway_cache_miss_flow")


def test_gateway_reports_provenance_of_a_simulated_answer():
    """A stand-in answer must not be billed or presented as a model response."""
    client = _client(
        completion={
            "content": "SIMULATED: no model answered",
            "model_used": "ollama/qwen3.5:4b (stand-in)",
            "provider": "none",
            "status": "simulated",
            "tokens_used": 0,
            "metadata": {"attempted": [{"tier": "local_slm", "outcome": "no answer"}]},
        }
    )
    body = client.post("/api/gateway/chat", json={"prompt": "Hello there"}).json()
    assert body["status"] == "simulated"
    assert body["provider_used"] == "none"
    assert body["model"].endswith("(stand-in)")
    assert body["cost_usd"] == 0.0
    print("[PASS] test_gateway_reports_provenance_of_a_simulated_answer")


def test_gateway_says_whose_key_paid_for_the_call():
    """The UI labels a request "byok" or "operator" so the visitor knows whether their
    own key or the host's was spent. The label only exists in the provider metadata
    today, so the response body has to carry it out."""
    client = _client(completion={
        "content": "[stub] answer that is comfortably longer than twenty characters",
        "model_used": "openai/gpt-4o-mini",
        "provider": "openai",
        "status": "success",
        "tokens_used": 42,
        "metadata": {"attempted": [], "key_source": "byok"},
    })
    body = client.post("/api/gateway/chat", json={"prompt": "Hello there"}).json()
    assert body["key_source"] == "byok"

    local = _client()
    assert local.post("/api/gateway/chat", json={"prompt": "Hello there"}).json()["key_source"] is None

    print("[PASS] test_gateway_says_whose_key_paid_for_the_call")


def test_gateway_cache_hit_flow():
    client = _client(
        cache_hit={
            "response": "cached answer",
            "metadata": {"model": "ollama/qwen3.5:4b", "provider": "local_slm", "tokens": 42},
            "similarity": 0.97,
        }
    )
    resp = client.post("/api/gateway/chat", json={"prompt": "Hello there"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cache_hit"] is True
    assert body["status"] == "cached"
    assert body["response"] == "cached answer"
    assert body["destination"] == "memory_vault"
    assert body["model"] == "ollama/qwen3.5:4b"
    assert "evaluation_score" not in body
    print("[PASS] test_gateway_cache_hit_flow")


def test_gateway_returns_its_own_signal_trail():
    client = _client()
    body = client.post("/api/gateway/chat", json={"prompt": "Hello there"}).json()
    assert [packet["event"] for packet in body["signals"]] == [
        "CACHE_MISS",
        "ROUTING_SIGNAL",
        "MODEL_EXECUTION",
        "EVALUATION",
        "COMPLETION",
    ]
    evaluation = body["signals"][3]["metadata"]
    assert evaluation["passed"] is True
    assert evaluation["checks"] == {"non_empty": True, "real_model_answered": True}
    print("[PASS] test_gateway_returns_its_own_signal_trail")


def test_evaluation_reports_a_stand_in_as_failed():
    """No model answered, so the evaluation step must say so instead of scoring it."""
    client = _client(
        completion={
            "content": "SIMULATED: no model answered",
            "model_used": "ollama/qwen3.5:4b (stand-in)",
            "provider": "none",
            "status": "simulated",
            "tokens_used": 0,
            "metadata": {"attempted": []},
        }
    )
    body = client.post("/api/gateway/chat", json={"prompt": "Hello there"}).json()
    evaluation = body["signals"][3]["metadata"]
    assert evaluation["passed"] is False
    assert evaluation["checks"]["real_model_answered"] is False
    print("[PASS] test_evaluation_reports_a_stand_in_as_failed")


def test_gateway_caches_with_provenance_metadata():
    client = _client()
    client.post("/api/gateway/chat", json={"prompt": "Hello there"})
    query, response, metadata = gateway_module.cache_service.stored[0]
    assert query == "Hello there"
    assert metadata["model"] == "ollama/qwen3.5:4b"
    assert metadata["provider"] == "local_slm"
    assert metadata["tokens"] == 42
    assert "evaluation_score" not in metadata
    print("[PASS] test_gateway_caches_with_provenance_metadata")


def test_websocket_emits_step_packets():
    client = _client()
    with client.websocket_connect("/ws/signals") as ws:
        client.post("/api/gateway/chat", json={"prompt": "Hello there"})
        events = [ws.receive_json()["event"] for _ in range(5)]
    assert events == [
        "CACHE_MISS",
        "ROUTING_SIGNAL",
        "MODEL_EXECUTION",
        "EVALUATION",
        "COMPLETION",
    ]
    print("[PASS] test_websocket_emits_step_packets")


if __name__ == "__main__":
    test_gateway_cache_miss_flow()
    test_gateway_reports_when_the_answer_was_cut_short_by_the_token_budget()
    test_a_cut_off_answer_is_never_stored_in_the_cache()
    test_a_stand_in_answer_is_never_stored_in_the_cache()
    test_gateway_asks_for_plain_bounded_prose()
    test_gateway_reports_provenance_of_a_simulated_answer()
    test_gateway_says_whose_key_paid_for_the_call()
    test_gateway_cache_hit_flow()
    test_gateway_returns_its_own_signal_trail()
    test_evaluation_reports_a_stand_in_as_failed()
    test_gateway_caches_with_provenance_metadata()
    test_websocket_emits_step_packets()
    print("\nALL GATEWAY / TELEMETRY TESTS PASSED!")
