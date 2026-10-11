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

import main
import app.api.gateway as gateway_module


class StubCache:
    def __init__(self, hit=None):
        self.hit = hit
        self.stored = []

    async def get(self, query):
        return self.hit

    async def set(self, query, response, metadata=None):
        self.stored.append((query, response))


class StubProvider:
    async def execute_completion(self, model, messages, **kwargs):
        return {
            "content": f"[stub:{model}] {messages[-1]['content']}",
            "model_used": model,
            "provider": "local_slm",
            "status": "success",
        }


def _client(cache_hit=None):
    gateway_module.cache_service = StubCache(hit=cache_hit)
    gateway_module.provider_manager = StubProvider()
    return TestClient(main.app)


def test_gateway_cache_miss_flow():
    client = _client()
    resp = client.post("/api/gateway/chat", json={"prompt": "Hello there"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cache_hit"] is False
    assert body["response"].startswith("[stub:")
    assert body["destination"] == "local_slm"
    print("[PASS] test_gateway_cache_miss_flow")


def test_gateway_cache_hit_flow():
    client = _client(cache_hit={"response": "cached answer", "metadata": {}, "similarity": 0.97})
    resp = client.post("/api/gateway/chat", json={"prompt": "Hello there"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["cache_hit"] is True
    assert body["response"] == "cached answer"
    assert body["destination"] == "memory_vault"
    print("[PASS] test_gateway_cache_hit_flow")


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
    test_gateway_cache_hit_flow()
    test_websocket_emits_step_packets()
    print("\nALL GATEWAY / TELEMETRY TESTS PASSED!")
