"""
Unit tests for SmartRouter and ProviderManager. Every provider tier is stubbed so
the suite makes no network calls and never spends an API key.
Runnable via `python -m pytest` or directly as a script.
"""

import asyncio
import os
import sys

# Ensure backend root is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import app.core.providers as providers_module
from app.core.providers import ProviderManager
from app.core.router import SmartRouter


def test_smart_router_easy_queries():
    """Verify simple/short queries route to Local SLM with 0.0 estimated cost."""
    router = SmartRouter()

    easy_queries = [
        "Hello, how are you?",
        "What is the capital of France?",
        "Define photosynthesis in one sentence.",
        "Tell me a short joke.",
    ]

    for q in easy_queries:
        decision = router.evaluate_route(q)
        assert decision["destination"] == "local_slm", f"Failed for query: {q}. Got: {decision}"
        assert decision["estimated_cost"] == 0.0, f"Expected 0 cost for easy query, got: {decision['estimated_cost']}"
        assert decision["complexity_metrics"]["is_hard"] is False, f"Query marked hard unexpectedly: {q}"
        assert "ollama" in decision["model"], f"Expected a local model, got {decision['model']}"

    print("[PASS] test_smart_router_easy_queries")


def test_smart_router_hard_queries():
    """Verify complex reasoning/code/architecture queries route to Cloud Fortress."""
    router = SmartRouter()

    hard_queries = [
        "Write an async Python algorithm with concurrency locks to handle database transactions and explain how to prevent deadlocks in distributed architectures.",
        "Refactor this SQL schema migration for high-load sharding and analyze the index optimization: ```sql SELECT * FROM users JOIN orders ON users.id = orders.user_id; ```",
        "Explain the mathematical proof of the Riemann hypothesis and its cryptographic implications for asymmetric RSA key encryption.",
    ]

    for q in hard_queries:
        decision = router.evaluate_route(q)
        assert decision["destination"] == "cloud_fortress", f"Failed for complex query: {q}. Got: {decision}"
        assert decision["estimated_cost"] > 0.0, f"Expected non-zero cost for cloud query: {decision}"
        assert decision["complexity_metrics"]["is_hard"] is True, f"Query should be marked hard: {q}"

    print("[PASS] test_smart_router_hard_queries")


def test_smart_router_premium_tier():
    """Verify premium tier with hard query routes to Claude fortress."""
    router = SmartRouter()
    hard_code_query = (
        "Architect a microservices security model with OAuth2, JWT validation, and RBAC policies. "
        "Include a complete multi-step threat model analyzing potential exploit vectors."
    )
    decision = router.evaluate_route(hard_code_query, user_tier="premium")
    assert decision["destination"] == "cloud_fortress"
    assert "claude" in decision["model"]
    assert decision["estimated_cost"] > 0.005

    print("[PASS] test_smart_router_premium_tier")


def test_smart_router_uses_configured_models():
    """Router must read model names from settings, not hardcode them."""
    from config import settings

    router = SmartRouter()
    assert router.default_local_model == f"ollama/{settings.OLLAMA_MODEL}"
    assert router.default_cloud_model == settings.DEFAULT_GEMINI_MODEL

    print("[PASS] test_smart_router_uses_configured_models")


def test_provider_local_success():
    """A healthy Ollama answer is reported as success with its real token count."""
    manager = ProviderManager()

    async def fake_ollama(messages, model_name):
        return {"content": "LOCAL PULSE OK", "tokens": 42, "model": f"ollama/{model_name}"}

    manager._call_ollama_direct = fake_ollama
    result = asyncio.run(
        manager.execute_completion(model="ollama/qwen3.5:4b", messages=[{"role": "user", "content": "hi"}])
    )
    assert result["status"] == "success"
    assert result["provider"] == "local_slm"
    assert result["fallback_triggered"] is False
    assert result["tokens_used"] == 42
    assert result["content"] == "LOCAL PULSE OK"

    print("[PASS] test_provider_local_success")


def test_provider_stand_in_is_labelled():
    """With every tier down, the gateway must say so instead of pretending to be a model."""
    manager = ProviderManager()

    async def no_ollama(messages, model_name):
        return None

    async def no_deepseek(messages, model_name=None):
        return None

    original_litellm_flag = providers_module.LITELLM_AVAILABLE
    providers_module.LITELLM_AVAILABLE = False
    manager._call_ollama_direct = no_ollama
    manager._call_deepseek_direct = no_deepseek
    manager.get_gemini_key = lambda: None

    try:
        result = asyncio.run(
            manager.execute_completion(model="ollama/qwen3.5:4b", messages=[{"role": "user", "content": "hi"}])
        )
    finally:
        providers_module.LITELLM_AVAILABLE = original_litellm_flag

    assert result["status"] == "simulated"
    assert result["provider"] == "none"
    assert result["fallback_triggered"] is True
    assert result["tokens_used"] == 0
    assert result["model_used"].endswith("(stand-in)")
    assert [entry["tier"] for entry in result["metadata"]["attempted"]] == [
        "local_slm", "gemini", "deepseek", "litellm",
    ]

    print("[PASS] test_provider_stand_in_is_labelled")


def test_provider_gemini_is_reported_as_cloud():
    """When Gemini answers, provenance must be cloud_fortress even if local was requested."""
    manager = ProviderManager()

    async def no_ollama(messages, model_name):
        return None

    async def fake_gemini(messages, model_name):
        return {"content": "from gemini", "tokens": 7, "model": f"gemini/{model_name}"}

    manager._call_ollama_direct = no_ollama
    manager._call_gemini_direct = fake_gemini
    manager.get_gemini_key = lambda: "test-key"

    result = asyncio.run(
        manager.execute_completion(model="ollama/qwen3.5:4b", messages=[{"role": "user", "content": "hi"}])
    )
    assert result["provider"] == "cloud_fortress"
    assert result["status"] == "fallback"
    assert result["fallback_triggered"] is True
    assert result["tokens_used"] == 7

    print("[PASS] test_provider_gemini_is_reported_as_cloud")


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Captures the outgoing payload so tests can assert on what Ollama is sent."""

    def __init__(self, payload):
        self._payload = payload
        self.posts = []

    def __call__(self, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        self.posts.append({"url": url, "json": json, "headers": headers or {}})
        return _FakeResponse(self._payload)


def test_ollama_request_disables_thinking_and_caps_context():
    """Reasoning models answer nothing until ~200 hidden tokens are generated, which
    is unusable when inference falls back to CPU, so the payload must suppress it."""
    from config import settings

    manager = ProviderManager()
    client = _FakeAsyncClient(
        {"message": {"role": "assistant", "content": "LOCAL PULSE OK"}, "eval_count": 12, "prompt_eval_count": 5}
    )
    original = providers_module.httpx.AsyncClient
    providers_module.httpx.AsyncClient = client
    try:
        result = asyncio.run(manager._call_ollama_direct([{"role": "user", "content": "hi"}], "ollama/gemma4:e2b"))
    finally:
        providers_module.httpx.AsyncClient = original

    sent = client.posts[0]["json"]
    assert sent["model"] == "gemma4:e2b"
    assert sent["think"] is False
    assert sent["options"] == {"num_ctx": settings.OLLAMA_NUM_CTX}
    assert sent["keep_alive"] == settings.OLLAMA_KEEP_ALIVE
    assert result["tokens"] == 17
    assert result["content"] == "LOCAL PULSE OK"

    print("[PASS] test_ollama_request_disables_thinking_and_caps_context")


def test_ollama_empty_answer_counts_as_a_miss():
    """A 200 with no visible content must fall through the cascade, not report success."""
    manager = ProviderManager()
    client = _FakeAsyncClient({"message": {"role": "assistant", "content": "   "}, "eval_count": 0})
    original = providers_module.httpx.AsyncClient
    providers_module.httpx.AsyncClient = client
    try:
        result = asyncio.run(manager._call_ollama_direct([{"role": "user", "content": "hi"}], "ollama/gemma4:e2b"))
    finally:
        providers_module.httpx.AsyncClient = original

    assert result is None

    print("[PASS] test_ollama_empty_answer_counts_as_a_miss")


def test_deepseek_is_called_directly_with_its_own_key():
    """DeepSeek must not inherit credentials from OPENAI_API_KEY, so it is called
    over its own endpoint with its own bearer token."""
    import os
    from config import settings

    manager = ProviderManager()
    client = _FakeAsyncClient(
        {"choices": [{"message": {"role": "assistant", "content": "DEEPSEEK PULSE OK"}}],
         "usage": {"total_tokens": 42}}
    )
    original_key = settings.DEEPSEEK_API_KEY
    original_env = os.environ.pop("DEEPSEEK_API_KEY", None)
    original_client = providers_module.httpx.AsyncClient
    settings.DEEPSEEK_API_KEY = "test-deepseek-key"
    providers_module.httpx.AsyncClient = client
    try:
        result = asyncio.run(manager._call_deepseek_direct([{"role": "user", "content": "hi"}]))
    finally:
        settings.DEEPSEEK_API_KEY = original_key
        if original_env is not None:
            os.environ["DEEPSEEK_API_KEY"] = original_env
        providers_module.httpx.AsyncClient = original_client

    sent = client.posts[0]
    assert sent["url"] == f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
    assert sent["json"]["model"] == settings.DEFAULT_DEEPSEEK_MODEL
    assert sent["headers"]["Authorization"] == "Bearer test-deepseek-key"
    assert result["content"] == "DEEPSEEK PULSE OK"
    assert result["tokens"] == 42
    assert result["model"] == f"deepseek/{settings.DEFAULT_DEEPSEEK_MODEL}"

    print("[PASS] test_deepseek_is_called_directly_with_its_own_key")


def test_deepseek_without_a_key_never_leaves_the_process():
    """No key means the tier is skipped outright — no request, no leaked credential."""
    import os
    from config import settings

    manager = ProviderManager()
    original_key = settings.DEEPSEEK_API_KEY
    original_env = os.environ.pop("DEEPSEEK_API_KEY", None)
    settings.DEEPSEEK_API_KEY = None
    try:
        result = asyncio.run(manager._call_deepseek_direct([{"role": "user", "content": "hi"}]))
    finally:
        settings.DEEPSEEK_API_KEY = original_key
        if original_env is not None:
            os.environ["DEEPSEEK_API_KEY"] = original_env

    assert result is None

    print("[PASS] test_deepseek_without_a_key_never_leaves_the_process")


def test_litellm_model_names_get_provider_prefixes():
    """LiteLLM rejects bare model names, so the cascade must prefix them."""
    manager = ProviderManager()
    assert manager._as_litellm_model("gpt-4o-mini") == "openai/gpt-4o-mini"
    assert manager._as_litellm_model("claude-3-5-sonnet-20241022") == "anthropic/claude-3-5-sonnet-20241022"
    assert manager._as_litellm_model("openai/gpt-4o-mini") == "openai/gpt-4o-mini"

    # Premium routing must actually reach Claude first, not retry GPT.
    assert manager._litellm_candidates("claude-3-5-sonnet-20241022")[0] == "anthropic/claude-3-5-sonnet-20241022"

    # Local models are already handled by Tier A and must not be re-sent through LiteLLM.
    assert manager._litellm_candidates("ollama/qwen3.5:4b") == [
        "openai/gpt-4o-mini",
        "anthropic/claude-3-5-sonnet-20241022",
    ]

    print("[PASS] test_litellm_model_names_get_provider_prefixes")


if __name__ == "__main__":
    test_smart_router_easy_queries()
    test_smart_router_hard_queries()
    test_smart_router_premium_tier()
    test_smart_router_uses_configured_models()
    test_provider_local_success()
    test_provider_stand_in_is_labelled()
    test_provider_gemini_is_reported_as_cloud()
    test_ollama_request_disables_thinking_and_caps_context()
    test_ollama_empty_answer_counts_as_a_miss()
    test_deepseek_is_called_directly_with_its_own_key()
    test_deepseek_without_a_key_never_leaves_the_process()
    test_litellm_model_names_get_provider_prefixes()
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
