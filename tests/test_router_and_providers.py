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
from config import settings


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


def test_a_cloud_model_named_llama_is_never_sent_to_ollama():
    """Groq's default model is llama-3.3-70b-versatile. The local tier must be chosen by
    the ollama/ prefix alone, or the gateway would ask Ollama for a model it never pulled."""
    manager = ProviderManager()
    asked = []

    async def spy(messages, model_name):
        asked.append(model_name)
        return None

    manager._call_ollama_direct = spy
    manager.get_gemini_key = lambda byok=None: None
    providers_module.LITELLM_AVAILABLE = False

    result = asyncio.run(
        manager.execute_completion(model="groq/llama-3.3-70b-versatile", messages=[{"role": "user", "content": "hi"}])
    )

    assert asked == []
    assert result["status"] == "simulated"
    assert result["fallback_triggered"] is False
    print("[PASS] test_a_cloud_model_named_llama_is_never_sent_to_ollama")


def test_provider_local_success():
    """A healthy Ollama answer is reported as success with its real token count."""
    manager = ProviderManager()

    async def fake_ollama(messages, model_name):
        return {"content": "LOCAL PULSE OK", "tokens": 42, "model": f"ollama/{model_name}", "truncated": False}

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

    async def no_deepseek(messages, model_name=None, byok=None):
        return None

    original_litellm_flag = providers_module.LITELLM_AVAILABLE
    providers_module.LITELLM_AVAILABLE = False
    manager._call_ollama_direct = no_ollama
    manager._call_deepseek_direct = no_deepseek
    manager.get_gemini_key = lambda byok=None: None

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

    async def fake_gemini(messages, model_name, byok=None):
        return {"content": "from gemini", "tokens": 7, "model": f"gemini/{model_name}"}

    manager._call_ollama_direct = no_ollama
    manager._call_gemini_direct = fake_gemini
    manager.get_gemini_key = lambda byok=None: "test-key"

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

    async def get(self, url):
        self.posts.append({"url": url, "json": None, "headers": {}})
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
    assert sent["options"]["num_ctx"] == settings.OLLAMA_NUM_CTX
    assert sent["options"]["num_predict"] == settings.OLLAMA_NUM_PREDICT
    assert sent["keep_alive"] == settings.OLLAMA_KEEP_ALIVE
    assert result["tokens"] == 17
    assert result["content"] == "LOCAL PULSE OK"
    assert result["truncated"] is False

    print("[PASS] test_ollama_request_disables_thinking_and_caps_context")


def test_ollama_answer_cut_short_by_the_budget_is_marked_truncated():
    """A cap turns long answers into cut-off text, so the caller must be able to see
    that the model stopped for length rather than finishing its answer."""
    manager = ProviderManager()
    client = _FakeAsyncClient(
        {"message": {"role": "assistant", "content": "Semantic caching means"},
         "eval_count": 256, "prompt_eval_count": 20, "done_reason": "length"}
    )
    original = providers_module.httpx.AsyncClient
    providers_module.httpx.AsyncClient = client
    try:
        result = asyncio.run(manager._call_ollama_direct([{"role": "user", "content": "hi"}], "ollama/gemma4:e2b"))
    finally:
        providers_module.httpx.AsyncClient = original

    assert result["truncated"] is True

    print("[PASS] test_ollama_answer_cut_short_by_the_budget_is_marked_truncated")


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


def test_provider_is_chosen_from_the_routed_model_name():
    """LiteLLM routes by provider prefix, so the cascade must know which provider a
    bare model name belongs to before it can reach the right one first."""
    manager = ProviderManager()

    assert manager._provider_for_model("gpt-4o-mini") == "openai"
    assert manager._provider_for_model("claude-3-5-sonnet-20241022") == "anthropic"
    assert manager._provider_for_model("grok-2-latest") == "xai"
    assert manager._provider_for_model("groq/llama-3.3-70b-versatile") == "groq"
    assert manager._provider_for_model("ollama/gemma4:e2b") is None

    print("[PASS] test_provider_is_chosen_from_the_routed_model_name")


def test_cloud_candidates_only_include_providers_that_have_a_key(monkeypatch):
    """A candidate without a key would either fail or, worse, bill an unrelated
    account, so providers with no BYOK and no host key must not be offered."""
    manager = ProviderManager()

    assert manager._cloud_candidates("claude-3-5-sonnet-20241022", None) == []

    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "host-anthropic-key", raising=False)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "host-openai-key", raising=False)
    candidates = manager._cloud_candidates("claude-3-5-sonnet-20241022", None)

    # The routed model's provider leads, and every name carries its provider prefix.
    assert candidates[0]["name"] == "anthropic"
    assert candidates[0]["model"] == f"anthropic/{settings.DEFAULT_ANTHROPIC_MODEL}"
    assert candidates[0]["key_source"] == "operator"
    assert {c["name"] for c in candidates} == {"anthropic", "openai"}

    print("[PASS] test_cloud_candidates_only_include_providers_that_have_a_key")


def test_a_visitors_key_selects_that_provider_and_marks_the_source(monkeypatch):
    """With no host keys at all, a caller-supplied OpenAI key must be what unlocks
    the LiteLLM tier, and the provenance has to say the visitor paid."""
    from app.core.credentials import BYOKCredentials

    manager = ProviderManager()
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None, raising=False)
    candidates = manager._cloud_candidates(
        "gpt-4o-mini", BYOKCredentials(openai_api_key="visitor-openai-key")
    )

    assert len(candidates) == 1
    assert candidates[0] == {
        "name": "openai",
        "model": f"openai/{settings.DEFAULT_OPENAI_MODEL}",
        "api_key": "visitor-openai-key",
        "key_source": "byok",
    }

    print("[PASS] test_a_visitors_key_selects_that_provider_and_marks_the_source")


def test_host_provider_status_reports_keys_without_exposing_them():
    """The UI shows which providers the host can already reach; it must never receive
    the key itself, only a boolean."""
    manager = ProviderManager()
    settings.GROQ_API_KEY = "host-groq-key"
    try:
        statuses = manager.host_provider_status()
    finally:
        settings.GROQ_API_KEY = None

    groq = next(s for s in statuses if s["provider"] == "groq")
    assert groq["host_key_configured"] is True
    assert groq["env_var"] == "GROQ_API_KEY"
    assert "key" not in groq
    assert "host-groq-key" not in str(statuses)

    print("[PASS] test_host_provider_status_reports_keys_without_exposing_them")


def test_local_models_are_read_from_the_ollama_daemon():
    """The model picker must show what this machine actually pulled, not a fixed list."""
    manager = ProviderManager()
    client = _FakeAsyncClient({"models": [{"name": "gemma4:e2b", "size": 1234}, {"name": "nomic-embed-text"}]})
    original = providers_module.httpx.AsyncClient
    providers_module.httpx.AsyncClient = client
    try:
        result = asyncio.run(manager.list_local_models())
    finally:
        providers_module.httpx.AsyncClient = original

    assert result["available"] is True
    assert [m["name"] for m in result["models"]] == ["gemma4:e2b", "nomic-embed-text"]
    assert client.posts[0]["url"].endswith("/api/tags")

    print("[PASS] test_local_models_are_read_from_the_ollama_daemon")


def test_models_endpoint_serves_the_catalog_and_host_key_status(monkeypatch):
    """The settings panel reads one endpoint for both, so the gateway must expose it
    without the suite touching a live daemon."""
    import app.api.gateway as gateway_module

    class _StubManager:
        async def list_local_models(self):
            return {"available": True, "base_url": "http://localhost:11434", "models": [{"name": "gemma4:e2b", "size": 1}]}

        def host_provider_status(self):
            return [{"provider": "gemini", "env_var": "GEMINI_API_KEY", "host_key_configured": False}]

    monkeypatch.setattr(gateway_module, "provider_manager", _StubManager())
    catalog = asyncio.run(gateway_module.get_model_catalog())

    assert catalog.ollama_available is True
    assert catalog.models[0].name == "gemma4:e2b"
    assert catalog.providers[0].env_var == "GEMINI_API_KEY"

    print("[PASS] test_models_endpoint_serves_the_catalog_and_host_key_status")


def _gate_manager(calls):
    """A manager whose local tier is down but whose cloud tiers have keys, so any
    fallback attempt is observable."""
    manager = ProviderManager()

    async def local_silent(messages, model):
        return None

    async def fake_gemini(messages, model, byok=None):
        calls["gemini"] += 1
        return {"content": "cloud answer", "model": "gemini-x", "tokens": 1}

    async def fake_deepseek(messages, byok=None):
        calls["deepseek"] += 1
        return {"content": "cloud answer", "model": "deepseek-chat", "tokens": 1}

    manager._call_ollama_direct = local_silent
    manager.get_gemini_key = lambda byok=None: "fake-key"
    manager._call_gemini_direct = fake_gemini
    manager.get_deepseek_key = lambda byok=None: "fake-key"
    manager._call_deepseek_direct = fake_deepseek
    return manager


def test_local_only_keeps_document_context_off_cloud_tiers(monkeypatch):
    """When retrieved chunks ride in the messages and the local model is down, the
    answer must be the labelled stand-in, never a cloud fallback with the documents."""
    monkeypatch.setattr(providers_module, "LITELLM_AVAILABLE", False)
    calls = {"gemini": 0, "deepseek": 0}
    manager = _gate_manager(calls)

    messages = [{"role": "user", "content": "Context: private handbook text\n\nQuestion: hi"}]
    result = asyncio.run(manager.execute_completion("ollama/gemma4:e2b", messages, local_only=True))

    assert result["status"] == "simulated"
    assert calls == {"gemini": 0, "deepseek": 0}
    assert any(a["tier"] == "cloud" and a["outcome"].startswith("skipped") for a in result["metadata"]["attempted"])


def test_without_local_only_the_cascade_still_falls_back_to_cloud(monkeypatch):
    """The privacy flag must be the only thing that blocks the fallback: plain
    local failures keep reaching cloud tiers as before."""
    monkeypatch.setattr(providers_module, "LITELLM_AVAILABLE", False)
    calls = {"gemini": 0, "deepseek": 0}
    manager = _gate_manager(calls)

    result = asyncio.run(manager.execute_completion("ollama/gemma4:e2b", [{"role": "user", "content": "hi"}]))

    assert result["status"] == "fallback"
    assert result["provider"] == "cloud_fortress"
    assert calls["gemini"] == 1


def test_the_stand_in_does_not_echo_the_whole_prompt(monkeypatch):
    """A pasted file or a retrieved document lives in the prompt, and the stand-in
    used to repeat all of it back into the chat bubble and the SSE stream."""
    monkeypatch.setattr(providers_module, "LITELLM_AVAILABLE", False)
    manager = ProviderManager()

    async def local_silent(messages, model):
        return None

    manager._call_ollama_direct = local_silent
    manager.get_gemini_key = lambda byok=None: None
    manager.get_deepseek_key = lambda byok=None: None

    long_prompt = "handbook page text " * 400
    result = asyncio.run(manager.execute_completion("ollama/gemma4:e2b", [{"role": "user", "content": long_prompt}]))

    assert result["status"] == "simulated"
    assert "…" in result["content"]
    # A 7200-char prompt must not become a 7200-char bubble: the stand-in stays
    # roughly the size of its own explanation, whatever the caller pasted.
    assert len(result["content"]) < len(long_prompt) / 4


if __name__ == "__main__":
    test_smart_router_easy_queries()
    test_smart_router_hard_queries()
    test_smart_router_premium_tier()
    test_smart_router_uses_configured_models()
    test_a_cloud_model_named_llama_is_never_sent_to_ollama()
    test_provider_local_success()
    test_provider_stand_in_is_labelled()
    test_provider_gemini_is_reported_as_cloud()
    test_ollama_request_disables_thinking_and_caps_context()
    test_ollama_answer_cut_short_by_the_budget_is_marked_truncated()
    test_ollama_empty_answer_counts_as_a_miss()
    test_deepseek_is_called_directly_with_its_own_key()
    test_deepseek_without_a_key_never_leaves_the_process()
    test_provider_is_chosen_from_the_routed_model_name()
    test_host_provider_status_reports_keys_without_exposing_them()
    test_local_models_are_read_from_the_ollama_daemon()
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
