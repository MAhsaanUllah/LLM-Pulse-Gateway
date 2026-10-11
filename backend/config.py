from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "LLM Pulse Gateway"
    DEBUG: bool = True
    PORT: int = 8000

    # Redis Cache Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # Qdrant Vector Store Configuration
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # Ollama Local SLM Configuration
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Cloud LLM API Keys
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
