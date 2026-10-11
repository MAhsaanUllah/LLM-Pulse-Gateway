from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class GatewayRequest(BaseModel):
    prompt: str = Field(..., description="User prompt or instruction")
    tier: str = Field(default="standard", description="User subscription/priority tier (standard, premium)")
    stream: bool = Field(default=False, description="Whether to stream response")


class StructuredPulseResponse(BaseModel):
    query: str
    response: str
    destination: str
    model: str
    latency_ms: float
    cost_usd: float
    cache_hit: bool
    evaluation_score: Optional[float] = None
    signals: List[Dict[str, Any]] = []
