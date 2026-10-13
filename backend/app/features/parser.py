from pydantic import BaseModel, Field, field_validator
from typing import Literal, Optional, List, Dict, Any

from app.core.credentials import BYOKCredentials

# The local context window is 4096 tokens counting the prompt, so an unbounded
# history from the browser would crowd out the answer it is there to get.
MAX_HISTORY_TURNS = 12


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class GatewayRequest(BaseModel):
    prompt: str = Field(..., description="User prompt or instruction")
    tier: str = Field(default="standard", description="User subscription/priority tier (standard, premium)")
    history: List[ChatTurn] = Field(
        default_factory=list,
        description="Earlier turns of this conversation, oldest first; only the most recent are carried",
    )
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
    rag_used: bool = Field(
        default=False, description="True when retrieved knowledge-base chunks were attached to the prompt"
    )
    rag_chunks: int = Field(default=0, description="How many knowledge-base chunks were retrieved")
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


class CacheClearResponse(BaseModel):
    status: Literal["cleared"] = "cleared"
    cache_backend: str


class KnowledgeStoreRequest(BaseModel):
    text: str = Field(..., description="Document text to chunk and embed into the local knowledge base")
    source: str = Field(default="pasted", description="Label shown in provenance, e.g. a file or handbook name")

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class KnowledgeStoreResponse(BaseModel):
    status: Literal["stored"] = "stored"
    chunks_stored: int
    knowledge_backend: str


class KnowledgeClearResponse(BaseModel):
    status: Literal["cleared"] = "cleared"
    knowledge_backend: str
