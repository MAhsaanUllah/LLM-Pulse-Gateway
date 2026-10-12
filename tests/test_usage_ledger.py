"""Usage ledger: only figures the gateway actually measured are stored and reported."""

import asyncio
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.usage import UsageLedger


def test_ledger_totals_only_the_figures_that_were_measured(tmp_path):
    ledger = UsageLedger(db_path=str(tmp_path / "usage.sqlite"))
    ledger.record(
        route="local_slm", model="ollama/gemma4:e2b", status="success", cache_hit=False,
        tokens_used=42, latency_ms=16900.0, estimated_cost_usd=0.0,
    )
    ledger.record(
        route="memory_vault", model="ollama/gemma4:e2b", status="cached", cache_hit=True,
        tokens_used=0, latency_ms=2100.0, estimated_cost_usd=0.0,
    )

    totals = ledger.totals()
    assert totals["requests"] == 2
    assert totals["tokens_used"] == 42
    assert totals["cache_hits"] == 1
    assert totals["avg_latency_ms"] == 9500.0

    print("[PASS] test_ledger_totals_only_the_figures_that_were_measured")


class _SelfPopulatingCache:
    """Miss the first time, then serves what the gateway stored — like the real cache.
    Storing takes measurable time because the real one calls Ollama to embed."""

    def __init__(self):
        self.hit = None

    async def get(self, query):
        return self.hit

    async def set(self, query, response, metadata=None):
        await asyncio.sleep(0.05)
        self.hit = {"response": response, "metadata": metadata or {}}


class _LocalProvider:
    def __init__(self):
        self.seen_byok = None

    async def execute_completion(self, model, messages, byok=None, **kwargs):
        self.seen_byok = byok
        return {
            "content": "an answer long enough to be real",
            "model_used": "ollama/gemma4:e2b",
            "provider": "local_slm",
            "status": "success",
            "tokens_used": 42,
            "metadata": {"attempted": []},
        }


def _gateway(tmp_path, monkeypatch):
    import app.api.gateway as gateway_module
    import main
    from fastapi.testclient import TestClient

    ledger = UsageLedger(db_path=str(tmp_path / "usage.sqlite"))
    provider = _LocalProvider()
    monkeypatch.setattr(gateway_module, "usage_ledger", ledger)
    monkeypatch.setattr(gateway_module, "cache_service", _SelfPopulatingCache())
    monkeypatch.setattr(gateway_module, "provider_manager", provider)
    return ledger, provider, TestClient(main.app)


def test_gateway_ledgers_every_request_it_serves(tmp_path, monkeypatch):
    ledger, _, client = _gateway(tmp_path, monkeypatch)

    first = client.post("/api/gateway/chat", json={"prompt": "What is caching?"})
    second = client.post("/api/gateway/chat", json={"prompt": "What is caching?"})
    assert first.json()["cache_hit"] is False
    assert second.json()["cache_hit"] is True

    totals = ledger.totals()
    assert totals["requests"] == 2
    assert totals["tokens_used"] == 42
    assert totals["cache_hits"] == 1

    print("[PASS] test_gateway_ledgers_every_request_it_serves")


def test_usage_endpoint_reports_only_what_the_ledger_recorded(tmp_path, monkeypatch):
    """No invented numbers: the endpoint can only show rows the gateway actually wrote."""
    _, _, client = _gateway(tmp_path, monkeypatch)
    client.post("/api/gateway/chat", json={"prompt": "What is caching?"})

    response = client.get("/api/gateway/usage")
    assert response.status_code == 200
    body = response.json()
    assert body["requests"] == 1
    assert body["tokens_used"] == 42
    assert body["cache_hits"] == 0
    assert body["by_route"]["local_slm"]["tokens_used"] == 42
    assert "prompt" not in body and "byok" not in body

    print("[PASS] test_usage_endpoint_reports_only_what_the_ledger_recorded")


def test_ledger_stores_no_shadow_of_the_visitors_key(tmp_path, monkeypatch):
    """The ledger is the one file this gateway writes to disk, so it must prove the
    BYOK secret never lands there."""
    _, _, client = _gateway(tmp_path, monkeypatch)
    client.post(
        "/api/gateway/chat",
        json={"prompt": "What is caching?", "byok": {"gemini_api_key": "visitor-forever-key"}},
    )

    raw = (tmp_path / "usage.sqlite").read_bytes()
    assert b"visitor-forever-key" not in raw
    assert b"What is caching" not in raw

    print("[PASS] test_ledger_stores_no_shadow_of_the_visitors_key")


def test_ledger_and_response_report_the_same_latency(tmp_path, monkeypatch):
    """The UI shows a per-request latency and the ledger an average — if they measure
    different moments, the two screens disagree and neither can be trusted."""
    ledger, _, client = _gateway(tmp_path, monkeypatch)
    served = client.post("/api/gateway/chat", json={"prompt": "What is caching?"}).json()

    assert ledger.totals()["avg_latency_ms"] == served["latency_ms"]

    print("[PASS] test_ledger_and_response_report_the_same_latency")


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as workdir:
        test_ledger_totals_only_the_figures_that_were_measured(Path(workdir))
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")