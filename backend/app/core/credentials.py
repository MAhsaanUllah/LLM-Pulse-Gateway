from typing import Optional

from pydantic import BaseModel, Field


class BYOKCredentials(BaseModel):
    """Bring-your-own-key credentials supplied with a single request.

    The gateway treats these as a per-call secret: never written to disk, never
    included in telemetry, cache entries, logs, or responses. Blank fields simply
    mean "fall back to the operator's own key".
    """

    gemini_api_key: Optional[str] = Field(default=None, description="Visitor's own Google Gemini key")
    openai_api_key: Optional[str] = Field(default=None, description="Visitor's own OpenAI key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Visitor's own Anthropic (Claude) key")
    xai_api_key: Optional[str] = Field(default=None, description="Visitor's own xAI (Grok) key")
    deepseek_api_key: Optional[str] = Field(default=None, description="Visitor's own DeepSeek key")
    groq_api_key: Optional[str] = Field(default=None, description="Visitor's own Groq key")
    openrouter_api_key: Optional[str] = Field(default=None, description="Visitor's own OpenRouter key")
