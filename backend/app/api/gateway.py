from fastapi import APIRouter
import time
from typing import List

from app.api.websocket import SignalEvent, SignalPacket, stream_manager
from app.core.cache import cache_service
from app.core.providers import provider_manager
from app.core.router import smart_router
from app.features.evals import eval_engine
from app.features.parser import GatewayRequest, StructuredPulseResponse

router = APIRouter()


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
        },
    )

    # Step 3: Model execution
    try:
        await emit(SignalEvent.MODEL_EXECUTION, destination, destination, {"model": target_model})
        completion = await provider_manager.execute_completion(
            model=target_model,
            messages=[{"role": "user", "content": req.prompt}],
        )
    except Exception as exc:
        await emit(
            SignalEvent.ERROR,
            destination,
            "warden_tower",
            {"model": target_model, "error": str(exc)},
        )
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
        },
    )

    return StructuredPulseResponse(
        query=req.prompt,
        response=completion["content"],
        destination=destination,
        model=completion["model_used"],
        latency_ms=latency_ms,
        cost_usd=route_decision["estimated_cost"] if completion["status"] != "simulated" else 0.0,
        cache_hit=False,
        status=completion["status"],
        provider_used=completion["provider"],
        tokens_used=completion["tokens_used"],
        signals=[packet.model_dump() for packet in emitted],
    )
