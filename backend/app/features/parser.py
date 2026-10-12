from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from app.core.credentials import BYOKCredentials


class GatewayRequest(BaseModel):
    prompt: str = Field(..., description="User prompt or instruction")
    tier: str = Field(default="standard", description="User subscription/priority tier (standard, premium)")
    byok: Optional[BYOKCredentials] = Field(
        default=None, description="Caller-supplied cloud keys, honoured for this request only"
    )


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
    key_source: Optional[str] = Field(
        default=None,
        description='"byok" when the caller\'s key paid, "operator" when the host key did, None if no cloud key was used',
    )
    truncated: bool = Field(
        default=False, description="True when the answer hit the generated-token budget and was cut off"
    )
    signals: List[Dict[str, Any]] = []


class RouteUsage(BaseModel):
    requests: int
    tokens_used: int
    estimated_cost_usd: float


class UsageSummaryResponse(BaseModel):
    """Aggregates of the ledger rows this process actually wrote — nothing estimated."""

    requests: int
    tokens_used: int
    cache_hits: int
    avg_latency_ms: float
    estimated_cost_usd: float
    by_route: Dict[str, RouteUsage]


class LocalModel(BaseModel):
    name: str
    size: Optional[int] = None


class ProviderStatus(BaseModel):
    """Whether the operator's own environment already has a key for a provider."""

    provider: str
    env_var: str
    host_key_configured: bool


class ModelsResponse(BaseModel):
    """Local model detection plus which cloud providers the host can already reach."""

    ollama_available: bool
    base_url: str
    models: List[LocalModel] = []
    providers: List[ProviderStatus] = []
