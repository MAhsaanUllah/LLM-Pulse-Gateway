from typing import Optional

from pydantic import BaseModel, Field


class BYOKCredentials(BaseModel):
    """Bring-your-own-key credentials supplied with a single request.

    The gateway treats these as a per-call secret: never written to disk, never
    included in telemetry, cache entries, logs, or responses. Blank fields simply
    mean "fall back to the operator's own key".
    """

    gemini_api_key: Optional[str] = Field(default=None, description="Visitor's own Gemini key")
    deepseek_api_key: Optional[str] = Field(default=None, description="Visitor's own DeepSeek key")
