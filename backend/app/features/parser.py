from pydantic import BaseModel, Field
from typing import List, Dict, Any


class GatewayRequest(BaseModel):
    prompt: str = Field(..., description="User prompt or instruction")
    tier: str = Field(default="standard", description="User subscription/priority tier (standard, premium)")


class StructuredPulseResponse(BaseModel):
    query: str
    response: str
    destination: str
    model: str
    latency_ms: float
    cost_usd: float
    cache_hit: bool
    status: str = "success"
    provider_used: str = ""
    tokens_used: int = 0
    signals: List[Dict[str, Any]] = []
