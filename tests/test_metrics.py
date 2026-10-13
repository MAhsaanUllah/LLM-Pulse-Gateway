"""The metrics endpoint exposes the ledger as Prometheus gauges."""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest
from fastapi.testclient import TestClient

import main
from config import settings


@pytest.fixture(autouse=True)
def no_token(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_TOKEN", None, raising=False)


def test_metrics_exposes_the_ledger_as_prometheus_gauges():
    response = TestClient(main.app).get("/api/gateway/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "gateway_requests_total" in body
    assert "gateway_tokens_used_total" in body
    assert "gateway_cache_hits_total" in body
    # Prometheus text format: a gauge declares its type before its samples.
    assert "# TYPE gateway_requests_total gauge" in body
    print("[PASS] test_metrics_exposes_the_ledger_as_prometheus_gauges")


def test_metrics_is_gated_like_every_other_route(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_TOKEN", "s3cret-token")
    assert TestClient(main.app).get("/api/gateway/metrics").status_code == 401
    print("[PASS] test_metrics_is_gated_like_every_other_route")
