"""
Multi-turn memory: a request may carry the earlier turns of the conversation, and the
semantic cache must never answer a mid-conversation prompt from a context-free entry.
Runnable via `python -m pytest`.
"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from fastapi.testclient import TestClient

import app.api.gateway as gateway_module
import main
from app.features.parser import MAX_HISTORY_TURNS


class RecordingCache:
    def __init__(self, hit=None):
        self.hit = hit
        self.stored = []
        self.lookups = []

    async def get(self, query):
        self.lookups.append(query)
        return self.hit

    async def set(self, query, response, metadata=None):
        self.stored.append((query, response, metadata))


class RecordingProvider:
    def __init__(self):
        self.messages = []

    async def execute_completion(self, model, messages, **kwargs):
        self.messages.append(messages)
        return {
            "content": "[stub] two plus two is four, comfortably over twenty chars",
            "model_used": "ollama/gemma4:e2b",
            "provider": "local_slm",
            "status": "success",
            "tokens_used": 42,
            "metadata": {"attempted": []},
        }


def _wired(cache_hit=None):
    cache = RecordingCache(hit=cache_hit)
    provider = RecordingProvider()
    gateway_module.cache_service = cache
    gateway_module.provider_manager = provider
    return TestClient(main.app), cache, provider


def test_the_earlier_turns_reach_the_model_in_order():
    """A follow-up like 'and now in one word' only means anything if the model sees
    what came before, in order, with the roles still attached."""
    client, _, provider = _wired()
    client.post(
        "/api/gateway/chat",
        json={
            "prompt": "Now do the same in one word",
            "history": [
                {"role": "user", "content": "Name a primary colour"},
                {"role": "assistant", "content": "Blue"},
            ],
        },
    )

    sent = provider.messages[0]
    assert sent[0]["role"] == "system"
    assert sent[1:-1] == [
        {"role": "user", "content": "Name a primary colour"},
        {"role": "assistant", "content": "Blue"},
    ]
    assert sent[-1] == {"role": "user", "content": "Now do the same in one word"}
    print("[PASS] test_the_earlier_turns_reach_the_model_in_order")


def test_only_the_recent_turns_are_carried():
    """The context window is 4096 tokens including the prompt, so an endless history
    would silently crowd out the answer."""
    client, _, provider = _wired()
    history = [{"role": "user", "content": f"turn {i}"} for i in range(60)]
    client.post("/api/gateway/chat", json={"prompt": "and now?", "history": history})

    sent = provider.messages[0]
    assert len(sent) == MAX_HISTORY_TURNS + 2
    assert sent[-2]["content"] == "turn 59"
    assert sent[-3]["content"] == "turn 58"
    print("[PASS] test_only_the_recent_turns_are_carried")


def test_a_mid_conversation_prompt_is_not_answered_from_a_context_free_cache_entry():
    """The cache matches on the words of the last prompt alone, which is exactly the
    kind of text ('why?', 'in one word') that means something different per
    conversation — so a turn in progress must go to a model."""
    client, cache, provider = _wired(cache_hit={
        "response": "an old answer from a different conversation",
        "metadata": {"model": "ollama/gemma4:e2b", "provider": "local_slm"},
        "similarity": 0.99,
    })
    body = client.post(
        "/api/gateway/chat",
        json={"prompt": "and in one word?", "history": [{"role": "user", "content": "Explain caching"}]},
    ).json()

    assert cache.lookups == []
    assert body["status"] == "success"
    assert provider.messages, "the model should have been asked"
    print("[PASS] test_a_mid_conversation_prompt_is_not_answered_from_a_context_free_cache_entry")


def test_a_turn_in_progress_is_not_cached_on_its_own():
    """Storing 'and in one word? -> Blue' would serve 'Blue' to the next person who
    happens to ask anything in three words."""
    client, cache, _ = _wired()
    client.post(
        "/api/gateway/chat",
        json={"prompt": "and in one word?", "history": [{"role": "user", "content": "Name a primary colour"}]},
    )

    assert cache.stored == []
    print("[PASS] test_a_turn_in_progress_is_not_cached_on_its_own")


def test_a_first_turn_still_uses_the_cache_both_ways():
    """The memory work must not cost the single-turn accelerator it already had."""
    hit_client, hit_cache, _ = _wired(cache_hit={
        "response": "cached answer",
        "metadata": {"model": "ollama/gemma4:e2b", "provider": "local_slm"},
        "similarity": 0.96,
    })
    hit_body = hit_client.post("/api/gateway/chat", json={"prompt": "What is a vector database?"}).json()
    assert hit_body["status"] == "cached"
    assert hit_cache.lookups == ["What is a vector database?"]

    miss_client, miss_cache, _ = _wired()
    miss_client.post("/api/gateway/chat", json={"prompt": "What is a vector database?"})
    assert [q for q, _, _ in miss_cache.stored] == ["What is a vector database?"]
    print("[PASS] test_a_first_turn_still_uses_the_cache_both_ways")


def test_history_that_is_not_a_list_of_turns_is_refused():
    """An empty prompt is refused with 422 today, so a bad history should not be
    quietly ignored either — it would otherwise answer out of context."""
    client, _, provider = _wired()
    refused = client.post("/api/gateway/chat", json={"prompt": "hi", "history": [{"who": "me"}]})
    assert refused.status_code == 422
    assert provider.messages == []
    print("[PASS] test_history_that_is_not_a_list_of_turns_is_refused")


if __name__ == "__main__":
    test_the_earlier_turns_reach_the_model_in_order()
    test_only_the_recent_turns_are_carried()
    test_a_mid_conversation_prompt_is_not_answered_from_a_context_free_cache_entry()
    test_a_turn_in_progress_is_not_cached_on_its_own()
    test_a_first_turn_still_uses_the_cache_both_ways()
    test_history_that_is_not_a_list_of_turns_is_refused()
    print("\nALL MULTI-TURN TESTS PASSED!")
