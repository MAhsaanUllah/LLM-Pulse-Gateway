"""Keep the suite hermetic: no test may reach a paid cloud endpoint by accident."""
import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import app.core.providers as providers_module
from app.core.usage import UsageLedger
from config import settings

CREDENTIAL_VARS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "GOOGLE_API_KEY", "DEEPSEEK_API_KEY",
    "GROQ_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY",
)


@pytest.fixture(autouse=True)
def no_live_cloud_credentials(monkeypatch):
    for var in CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(settings, var, None, raising=False)
    monkeypatch.setattr(providers_module, "LITELLM_AVAILABLE", False)


@pytest.fixture(autouse=True)
def gates_open_for_the_suite(monkeypatch):
    """The suite talks to the endpoints as an unthrottled local caller: a token in
    the operator's .env must not turn every other test into a 401, and TestClients
    all share one client host, so a real window would 429 the suite at random."""
    monkeypatch.setattr(settings, "GATEWAY_TOKEN", None, raising=False)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 0, raising=False)


@pytest.fixture(autouse=True)
def cache_file_stays_in_tmp(tmp_path, monkeypatch):
    """The durable index writes real JSON. Left alone, a test run would edit the
    operator's own cache file and each test would inherit the last one's answers."""
    monkeypatch.setattr(settings, "CACHE_FILE_PATH", str(tmp_path / "semantic_cache.json"), raising=False)


@pytest.fixture(autouse=True)
def usage_ledger_writes_to_a_temp_file(tmp_path, monkeypatch):
    """The default ledger is the operator's real file; tests must not annotate it."""
    ledger = UsageLedger(db_path=str(tmp_path / "test-usage.sqlite"))
    monkeypatch.setattr("app.core.usage.usage_ledger", ledger)
    monkeypatch.setattr("app.api.gateway.usage_ledger", ledger)
