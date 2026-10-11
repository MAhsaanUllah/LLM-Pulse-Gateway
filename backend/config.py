from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "LLM Pulse Gateway"
    DEBUG: bool = True
    PORT: int = 8000

    # Redis Cache Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # Qdrant Vector Store Configuration
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # Semantic Cache / Embeddings
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    CACHE_COLLECTION: str = "semantic_cache"
    CACHE_SIMILARITY_THRESHOLD: float = 0.90

    # Ollama Local SLM Configuration
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Cloud LLM API Keys
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None


settings = Settings()
