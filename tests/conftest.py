"""Keep the suite hermetic: no test may reach a paid cloud endpoint by accident."""
import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import app.core.providers as providers_module
from config import settings

CREDENTIAL_VARS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "GOOGLE_API_KEY", "DEEPSEEK_API_KEY",
)


@pytest.fixture(autouse=True)
def no_live_cloud_credentials(monkeypatch):
    for var in CREDENTIAL_VARS:
        monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(settings, var, None, raising=False)
    monkeypatch.setattr(providers_module, "LITELLM_AVAILABLE", False)
