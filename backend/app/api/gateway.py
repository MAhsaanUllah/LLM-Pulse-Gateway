from fastapi import APIRouter
import time
from typing import List, Optional

from app.api.websocket import SignalEvent, SignalPacket, stream_manager
from app.core.cache import cache_service
from app.core.providers import provider_manager
from app.core.router import smart_router
from app.core.usage import usage_ledger
from app.features.evals import eval_engine
from app.features.parser import GatewayRequest, ModelsResponse, StructuredPulseResponse, UsageSummaryResponse

router = APIRouter()

# Left to itself, the local model answers with a markdown essay (~750 tokens: headings,
# bold runs, bullet nesting) that overruns the generated-token budget and reads badly in a
# chat bubble. The answer's shape has to be asked for, not hoped for.
ANSWER_STYLE = (
    "Answer in plain prose. No markdown: no headings, no bold, no bullet or numbered "
    "lists, no asterisks, no em dashes. Write two or three short paragraphs, at most "
    "120 words, and finish your answer."
)


@router.get("/gateway/models", response_model=ModelsResponse)
async def get_model_catalog() -> ModelsResponse:
    """Local models the Ollama daemon has pulled, plus host key status per provider."""
    local = await provider_manager.list_local_models()
    return ModelsResponse(
        ollama_available=local["available"],
        base_url=local["base_url"],
        models=local["models"],
        providers=provider_manager.host_provider_status(),
    )


@router.get("/gateway/usage", response_model=UsageSummaryResponse)
async def get_usage_summary() -> UsageSummaryResponse:
    return UsageSummaryResponse(**usage_ledger.totals(), by_route=usage_ledger.per_route())


@router.post("/gateway/chat", response_model=StructuredPulseResponse)
async def process_gateway_request(req: GatewayRequest) -> StructuredPulseResponse:
    start_time = time.time()
    emitted: List[SignalPacket] = []

    async def emit(event: SignalEvent, source: str, destination: str, metadata: dict) -> None:
        packet = SignalPacket(event=event, source=source, destination=destination, metadata=metadata)
        emitted.append(packet)
        await stream_manager.broadcast(packet)

    def elapsed_ms() -> float:
        return round((time.time() - start_time) * 1000, 2)

    def ledger(route: str, model: str, status: str, cache_hit: bool, tokens: int, cost: float,
               key_source: Optional[str] = None, latency: Optional[float] = None) -> None:
        usage_ledger.record(
            route=route,
            model=model,
            status=status,
            cache_hit=cache_hit,
            tokens_used=tokens,
            latency_ms=elapsed_ms() if latency is None else latency,
            estimated_cost_usd=cost,
            key_source=key_source,
        )

    # Step 1: Semantic cache check
    cached_result = await cache_service.get(req.prompt)
    if cached_result:
        cache_metadata = cached_result.get("metadata") or {}
        await emit(
            SignalEvent.CACHE_HIT,
            "warden_tower",
            "memory_vault",
            {
                "latency_ms": elapsed_ms(),
                "cost": 0.0,
                "similarity": cached_result.get("similarity"),
                "model": cache_metadata.get("model"),
            },
        )
        ledger("memory_vault", cache_metadata.get("model", "semantic-cache"), "cached", True, 0, 0.0)
        return StructuredPulseResponse(
            query=req.prompt,
            response=cached_result["response"],
            destination="memory_vault",
            model=cache_metadata.get("model", "semantic-cache"),
            latency_ms=elapsed_ms(),
            cost_usd=0.0,
            cache_hit=True,
            status="cached",
            provider_used=cache_metadata.get("provider", "memory_vault"),
            tokens_used=0,
            signals=[packet.model_dump() for packet in emitted],
        )

    await emit(SignalEvent.CACHE_MISS, "warden_tower", "memory_vault", {"latency_ms": elapsed_ms()})

    # Step 2: Smart route choice
    route_decision = smart_router.evaluate_route(req.prompt, user_tier=req.tier)
    destination = route_decision["destination"]
    target_model = route_decision["model"]
    await emit(
        SignalEvent.ROUTING_SIGNAL,
        "warden_tower",
        destination,
        {
            "model": target_model,
            "estimated_cost": route_decision["estimated_cost"],
            "reason": route_decision["reason"],
            "complexity": route_decision["complexity_metrics"],
        },
    )

    # Step 3: Model execution
    try:
        await emit(SignalEvent.MODEL_EXECUTION, destination, destination, {"model": target_model})
        completion = await provider_manager.execute_completion(
            model=target_model,
            messages=[
                {"role": "system", "content": ANSWER_STYLE},
                {"role": "user", "content": req.prompt},
            ],
            byok=req.byok,
        )
    except Exception as exc:
        await emit(
            SignalEvent.ERROR,
            destination,
            "warden_tower",
            {"model": target_model, "error": str(exc)},
        )
        ledger(destination, target_model, "error", False, 0, 0.0)
        raise

    # Step 4: Evaluation
    eval_result = await eval_engine.evaluate(completion["content"], completion["status"])
    await emit(
        SignalEvent.EVALUATION,
        destination,
        "warden_tower",
        {"passed": eval_result["passed"], "checks": eval_result["checks"], "status": completion["status"]},
    )

    # Step 5: Populate cache and emit completion
    latency_ms = elapsed_ms()
    truncated = bool(completion.get("truncated"))
    # A truncated answer is half a sentence, and a stand-in is the prompt echoed by
    # code — caching either would replay it forever as if a model had answered.
    if not truncated and completion["status"] != "simulated":
        await cache_service.set(
            req.prompt,
            completion["content"],
            {
                "model": completion["model_used"],
                "provider": completion["provider"],
                "status": completion["status"],
                "tokens": completion["tokens_used"],
            },
        )
    await emit(
        SignalEvent.COMPLETION,
        destination,
        "warden_tower",
        {
            "latency_ms": latency_ms,
            "model": completion["model_used"],
            "passed": eval_result["passed"],
            "tokens": completion["tokens_used"],
            "status": completion["status"],
            "truncated": truncated,
        },
    )

    estimated_cost = 0.0 if completion["status"] == "simulated" else route_decision["estimated_cost"]
    ledger(
        destination,
        completion["model_used"],
        completion["status"],
        False,
        completion["tokens_used"],
        estimated_cost,
        (completion.get("metadata") or {}).get("key_source"),
        latency=latency_ms,
    )

    return StructuredPulseResponse(
        query=req.prompt,
        response=completion["content"],
        destination=destination,
        model=completion["model_used"],
        latency_ms=latency_ms,
        cost_usd=estimated_cost,
        cache_hit=False,
        status=completion["status"],
        provider_used=completion["provider"],
        tokens_used=completion["tokens_used"],
        truncated=truncated,
        signals=[packet.model_dump() for packet in emitted],
    )
