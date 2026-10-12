from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "LLM Pulse Gateway"
    DEBUG: bool = True
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"

    # Qdrant Vector Store Configuration
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # Semantic Cache / Embeddings (served by Ollama, vector width comes from the model)
    EMBEDDING_MODEL: str = "nomic-embed-text"
    CACHE_COLLECTION: str = "semantic_cache"
    CACHE_SIMILARITY_THRESHOLD: float = 0.90

    # Ollama Local SLM Configuration
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma4:e2b"
    # Ollama defaults to the model's full context window (131k for these), which
    # allocates a KV cache that dominates latency when inference falls back to CPU.
    OLLAMA_NUM_CTX: int = 4096
    # Ollama unloads a model 5 minutes after the last request; a cold reload costs
    # ~12-50 s on CPU, which is longer than the inference budget below.
    OLLAMA_KEEP_ALIVE: str = "30m"
    # Uncapped, local models answer with ~750-token essays and dominate wall-clock
    # latency; this bounds generated tokens so a route stays inside the budget.
    OLLAMA_NUM_PREDICT: int = 256

    # Inference budget. A cold local model can spend ~20s just loading weights, so
    # this has to stay well above the first-token latency of the largest local model.
    INFERENCE_TIMEOUT_SECONDS: float = 90.0

    # Usage ledger (SQLite, standard library). Gitignored local file; delete it to reset.
    USAGE_DB_PATH: str = "data/usage.sqlite"

    # Gates. The gateway routes real money and real compute, so an open :8000 lets
    # anyone who can reach it spend the host's keys. Leave GATEWAY_TOKEN unset for
    # local-only work; set it before binding to anything but 127.0.0.1.
    GATEWAY_TOKEN: Optional[str] = None
    RATE_LIMIT_PER_MINUTE: int = 60
    # Cached answers expire so a stale or wrong one cannot replay forever. 0 = never.
    CACHE_TTL_SECONDS: int = 86400
    # Without Qdrant the index lives in this file, so a restart keeps its answers.
    CACHE_FILE_PATH: str = "data/semantic_cache.json"

    # Cloud LLM API Keys
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    XAI_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None

    # Default model per cloud provider (used by the LiteLLM fallback chain)
    DEFAULT_GEMINI_MODEL: str = "gemini-3.8-flash"
    DEFAULT_OPENAI_MODEL: str = "gpt-4o-mini"
    DEFAULT_ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    DEFAULT_GROQ_MODEL: str = "llama-3.3-70b-versatile"
    DEFAULT_XAI_MODEL: str = "grok-2-latest"
    DEFAULT_OPENROUTER_MODEL: str = "openai/gpt-4o-mini"

    # DeepSeek is OpenAI-compatible but called directly, so it needs no LiteLLM
    # and cannot be hijacked by an unrelated OPENAI_API_KEY in the environment.
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEFAULT_DEEPSEEK_MODEL: str = "deepseek-chat"


settings = Settings()
