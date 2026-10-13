"""
The gateway spends real money and real compute, so it needs gates: an optional
bearer token and a per-client rate limit. Runnable via `python -m pytest`.
"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest
from fastapi.testclient import TestClient

import app.core.guard as guard_module
import main
from config import settings


@pytest.fixture(autouse=True)
def fresh_rate_limiter(monkeypatch):
    """The limiter is process state; without this, a suite of unrelated tests
    would accumulate hits and start failing at random."""
    monkeypatch.setattr(guard_module.rate_limiter, "hits", {})
    yield


@pytest.fixture(autouse=True)
def no_token_and_a_roomy_window(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_TOKEN", None, raising=False)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 60, raising=False)


def test_the_gateway_is_open_when_no_token_is_configured():
    assert settings.GATEWAY_TOKEN is None
    assert TestClient(main.app).get("/api/gateway/usage").status_code == 200
    print("[PASS] test_the_gateway_is_open_when_no_token_is_configured")


def test_a_configured_token_rejects_callers_without_it(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_TOKEN", "s3cret-token")
    client = TestClient(main.app)
    assert client.get("/api/gateway/usage").status_code == 401
    assert client.post("/api/gateway/chat", json={"prompt": "hi"}).status_code == 401
    # Wiping the cache is the most destructive route, so it is gated too.
    assert client.post("/api/gateway/cache/clear").status_code == 401
    print("[PASS] test_a_configured_token_rejects_callers_without_it")


def test_the_exact_bearer_token_gets_through(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_TOKEN", "s3cret-token")
    client = TestClient(main.app)
    assert client.get("/api/gateway/usage", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200
    # A near miss is still a miss: no scheme, or the wrong value.
    assert client.get("/api/gateway/usage", headers={"Authorization": "s3cret-token"}).status_code == 401
    assert client.get("/api/gateway/usage", headers={"Authorization": "Bearer nope"}).status_code == 401
    print("[PASS] test_the_exact_bearer_token_gets_through")


def test_a_client_that_overruns_the_window_is_told_to_wait(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)
    client = TestClient(main.app)
    assert client.get("/api/gateway/usage").status_code == 200
    assert client.get("/api/gateway/usage").status_code == 200
    blocked = client.get("/api/gateway/usage")
    assert blocked.status_code == 429
    assert float(blocked.headers["retry-after"]) > 0
    print("[PASS] test_a_client_that_overruns_the_window_is_told_to_wait")


def test_the_rate_limit_is_per_client_not_global(monkeypatch):
    """One caller overrunning its window must not mute the next one: the window is
    keyed by client address. Asserted on the limiter itself because the TestClient
    cannot fake a second client address (starlette dropped that argument)."""
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    limiter = guard_module.RateLimiter()
    assert limiter.retry_after("127.0.0.1", now=0.0) is None
    assert limiter.retry_after("10.0.0.9", now=0.0) is None
    wait = limiter.retry_after("127.0.0.1", now=0.0)
    assert wait is not None and wait > 0
    print("[PASS] test_the_rate_limit_is_per_client_not_global")


def test_the_signal_socket_demands_the_token_when_one_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_TOKEN", "s3cret-token")
    with pytest.raises(Exception):
        with TestClient(main.app).websocket_connect("/ws/signals"):
            pass
    with TestClient(main.app).websocket_connect("/ws/signals?token=s3cret-token") as ws:
        assert ws is not None
    print("[PASS] test_the_signal_socket_demands_the_token_when_one_is_configured")


if __name__ == "__main__":
    test_the_gateway_is_open_when_no_token_is_configured()
    test_a_configured_token_rejects_callers_without_it(pytest.MonkeyPatch())
    test_the_exact_bearer_token_gets_through(pytest.MonkeyPatch())
    test_a_client_that_overruns_the_window_is_told_to_wait(pytest.MonkeyPatch())
    test_the_rate_limit_is_per_client_not_global(pytest.MonkeyPatch())
    test_the_signal_socket_demands_the_token_when_one_is_configured(pytest.MonkeyPatch())
    print("\nALL GATE / RATE-LIMIT TESTS PASSED!")
