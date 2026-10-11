"""
Unit and integration tests for SmartRouter and ProviderManager fallback engine.
Tests can be executed in any standard Python 3.10+ runtime without external dependencies.
"""

import sys
import os
import asyncio
from typing import Dict, Any

# Ensure backend root is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.router import SmartRouter, smart_router
from app.core.providers import ProviderManager, provider_manager


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
        assert "ollama" in decision["model"], f"Expected ollama model, got {decision['model']}"

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


def test_provider_manager_fallback():
    """Verify provider manager executes completion and handles simulated fallbacks."""
    import app.core.providers as providers_module

    # Force the offline built-in engine so the test never reaches a live provider.
    original_litellm_flag = providers_module.LITELLM_AVAILABLE
    providers_module.LITELLM_AVAILABLE = False

    async def _run_async_test():
        manager = ProviderManager()
        
        # Test normal execution
        res = await manager.execute_completion(
            model="ollama/llama3.2:3b",
            messages=[{"role": "user", "content": "Hello"}],
        )
        assert "content" in res
        assert res["provider"] == "local_slm"
        assert res["status"] in ["success", "fallback"]

        # Test model normalization
        normalized = manager._normalize_model_name("llama3.2:3b")
        assert normalized == "ollama/llama3.2:3b"

        cloud_norm = manager._normalize_model_name("gpt-4o-mini")
        assert cloud_norm == "gpt-4o-mini"

    try:
        asyncio.run(_run_async_test())
    finally:
        providers_module.LITELLM_AVAILABLE = original_litellm_flag
    print("[PASS] test_provider_manager_fallback")


if __name__ == "__main__":
    test_smart_router_easy_queries()
    test_smart_router_hard_queries()
    test_smart_router_premium_tier()
    test_provider_manager_fallback()
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
