"""BYOK: a caller-supplied cloud key is honoured per request and never persisted."""

import asyncio
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import app.core.providers as providers_module
from app.core.providers import ProviderManager
from app.core.credentials import BYOKCredentials
from config import settings
from fakes import FakeAsyncClient


def _run_with_fake_client(call, payload, status_code=200):
    client = FakeAsyncClient(payload, status_code=status_code)
    original = providers_module.httpx.AsyncClient
    providers_module.httpx.AsyncClient = client
    try:
        result = asyncio.run(call)
    finally:
        providers_module.httpx.AsyncClient = original
    return client, result


def test_byok_gemini_key_wins_over_the_operators_key():
    """The whole point of BYOK is that the visitor's key pays, not the host's."""
    manager = ProviderManager()
    original = settings.GEMINI_API_KEY
    settings.GEMINI_API_KEY = "operator-gemini-key"
    try:
        client, result = _run_with_fake_client(
            manager._call_gemini_direct(
                [{"role": "user", "content": "hi"}],
                "gemini/gemini-3.8-flash",
                BYOKCredentials(gemini_api_key="visitor-gemini-key"),
            ),
            {"candidates": [{"content": {"parts": [{"text": "BYOK GEMINI OK"}]}}],
             "usageMetadata": {"totalTokenCount": 9}},
        )
    finally:
        settings.GEMINI_API_KEY = original

    assert client.posts[0]["headers"]["x-goog-api-key"] == "visitor-gemini-key"
    assert result["content"] == "BYOK GEMINI OK"
    assert result["tokens"] == 9

    print("[PASS] test_byok_gemini_key_wins_over_the_operators_key")


def test_byok_deepseek_key_wins_over_the_operators_key():
    manager = ProviderManager()
    original = settings.DEEPSEEK_API_KEY
    settings.DEEPSEEK_API_KEY = "operator-deepseek-key"
    try:
        client, result = _run_with_fake_client(
            manager._call_deepseek_direct(
                [{"role": "user", "content": "hi"}],
                byok=BYOKCredentials(deepseek_api_key="visitor-deepseek-key"),
            ),
            {"choices": [{"message": {"content": "BYOK DEEPSEEK OK"}}],
             "usage": {"total_tokens": 11}},
        )
    finally:
        settings.DEEPSEEK_API_KEY = original

    assert client.posts[0]["headers"]["Authorization"] == "Bearer visitor-deepseek-key"
    assert result["content"] == "BYOK DEEPSEEK OK"
    assert result["tokens"] == 11

    print("[PASS] test_byok_deepseek_key_wins_over_the_operators_key")


def test_cascade_reaches_gemini_only_because_the_caller_brought_a_key():
    """With no operator key anywhere (conftest strips them), a visitor's key must still
    open the cloud tier — and the provenance must say whose key paid."""
    manager = ProviderManager()
    seen = {}

    async def no_ollama(messages, model_name):
        return None

    async def spy_gemini(messages, model_name, byok=None):
        seen["byok"] = byok
        return {"content": "served by visitor key", "tokens": 3, "model": f"gemini/{model_name}"}

    manager._call_ollama_direct = no_ollama
    manager._call_gemini_direct = spy_gemini

    result = asyncio.run(
        manager.execute_completion(
            model="ollama/gemma4:e2b",
            messages=[{"role": "user", "content": "hi"}],
            byok=BYOKCredentials(gemini_api_key="visitor-key"),
        )
    )

    assert seen["byok"].gemini_api_key == "visitor-key"
    assert result["provider"] == "cloud_fortress"
    assert result["metadata"]["key_source"] == "byok"

    print("[PASS] test_cascade_reaches_gemini_only_because_the_caller_brought_a_key")


class _RecordingProvider:
    def __init__(self):
        self.seen_byok = None

    async def execute_completion(self, model, messages, byok=None, **kwargs):
        self.seen_byok = byok
        return {
            "content": "served",
            "model_used": "gemini/gemini-3.8-flash",
            "provider": "cloud_fortress",
            "status": "success",
            "tokens_used": 5,
            "metadata": {"source": "gemini_direct", "key_source": "byok", "attempted": []},
        }


class _StubCache:
    def __init__(self):
        self.stored = []

    async def get(self, query):
        return None

    async def set(self, query, response, metadata=None):
        self.stored.append((query, response, metadata))


def _gateway_with(byok_payload):
    from fastapi.testclient import TestClient
    import app.api.gateway as gateway_module
    import main

    provider = _RecordingProvider()
    cache = _StubCache()
    gateway_module.provider_manager = provider
    gateway_module.cache_service = cache
    client = TestClient(main.app)
    payload = {"prompt": "Explain rate limiting", "tier": "premium"}
    if byok_payload is not None:
        payload["byok"] = byok_payload
    response = client.post("/api/gateway/chat", json=payload)
    return provider, cache, response


def test_gateway_forwards_the_visitors_key_to_the_provider():
    provider, _, response = _gateway_with({"gemini_api_key": "visitor-key"})
    assert response.status_code == 200
    assert provider.seen_byok.gemini_api_key == "visitor-key"

    print("[PASS] test_gateway_forwards_the_visitors_key_to_the_provider")


def test_visitors_key_never_comes_back_out_of_the_gateway():
    """The key crosses the boundary once, in the request body, and is echoed nowhere:
    not the response, not the WS signal trail, not the cached entry."""
    provider, cache, response = _gateway_with({"gemini_api_key": "visitor-secret-key"})
    assert provider.seen_byok.gemini_api_key == "visitor-secret-key"

    assert "visitor-secret-key" not in response.text
    for packet in response.json()["signals"]:
        assert "visitor-secret-key" not in str(packet)
    for _, _, metadata in cache.stored:
        assert "visitor-secret-key" not in str(metadata)

    print("[PASS] test_visitors_key_never_comes_back_out_of_the_gateway")


def test_rejected_byok_key_is_reported_with_its_status_code():
    """A bad visitor key must read as "your key was rejected (401)", not as a model
    that silently had nothing to say."""
    manager = ProviderManager()
    original_litellm = providers_module.LITELLM_AVAILABLE
    providers_module.LITELLM_AVAILABLE = False

    async def no_ollama(messages, model_name):
        return None

    manager._call_ollama_direct = no_ollama

    try:
        _, result = _run_with_fake_client(
            manager.execute_completion(
                model="ollama/gemma4:e2b",
                messages=[{"role": "user", "content": "hi"}],
                byok=BYOKCredentials(gemini_api_key="bad-key"),
            ),
            {"error": {"message": "API key not valid"}},
            status_code=401,
        )
    finally:
        providers_module.LITELLM_AVAILABLE = original_litellm

    gemini_entry = next(a for a in result["metadata"]["attempted"] if a["tier"] == "gemini")
    assert "401" in gemini_entry["outcome"]
    assert result["status"] == "simulated"

    print("[PASS] test_rejected_byok_key_is_reported_with_its_status_code")


def test_provider_never_logs_the_visitors_key_even_when_the_api_echoes_it(caplog):
    """OpenAI-compatible APIs paste the offending key back into their error body, so the
    gateway must redact before logging."""
    import logging

    manager = ProviderManager()
    client = FakeAsyncClient(
        {"error": {"message": "Incorrect API key provided: sk-visitor-secret"}},
        status_code=401,
        text="Incorrect API key provided: sk-visitor-secret",
    )
    original = providers_module.httpx.AsyncClient
    providers_module.httpx.AsyncClient = client
    with caplog.at_level(logging.WARNING):
        result = asyncio.run(
            manager._call_gemini_direct(
                [{"role": "user", "content": "hi"}],
                "gemini/gemini-3.8-flash",
                BYOKCredentials(gemini_api_key="sk-visitor-secret"),
            )
        )
    providers_module.httpx.AsyncClient = original

    assert result is None or "content" not in result
    assert "sk-visitor-secret" not in caplog.text

    print("[PASS] test_provider_never_logs_the_visitors_key_even_when_the_api_echoes_it")


def test_the_litellm_tier_never_echoes_the_visitors_key(caplog):
    """LiteLLM raises exceptions whose text contains the api_key it was given, so a
    failing cloud tier must not put that key in the log or in the cascade trace."""
    import logging

    manager = ProviderManager()

    class _EchoingLiteLLM:
        @staticmethod
        async def acompletion(**kwargs):
            raise Exception(f"BadRequest: invalid api key {kwargs['api_key']}")

    original_litellm = providers_module.litellm
    original_flag = providers_module.LITELLM_AVAILABLE
    providers_module.litellm = _EchoingLiteLLM()
    providers_module.LITELLM_AVAILABLE = True
    with caplog.at_level(logging.WARNING):
        result = asyncio.run(
            manager.execute_completion(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
                byok=BYOKCredentials(openai_api_key="sk-visitor-litellm-secret"),
            )
        )
    providers_module.litellm = original_litellm
    providers_module.LITELLM_AVAILABLE = original_flag

    assert "sk-visitor-litellm-secret" not in caplog.text
    assert "sk-visitor-litellm-secret" not in str(result)

    print("[PASS] test_the_litellm_tier_never_echoes_the_visitors_key")


if __name__ == "__main__":
    test_byok_gemini_key_wins_over_the_operators_key()
    test_byok_deepseek_key_wins_over_the_operators_key()
    test_cascade_reaches_gemini_only_because_the_caller_brought_a_key()
    test_gateway_forwards_the_visitors_key_to_the_provider()
    test_visitors_key_never_comes_back_out_of_the_gateway()
    test_rejected_byok_key_is_reported_with_its_status_code()