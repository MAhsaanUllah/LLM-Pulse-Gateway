from fastapi import APIRouter
import time

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

    # Step 1: Semantic cache check
    cached_result = await cache_service.get(req.prompt)
    if cached_result:
        latency = (time.time() - start_time) * 1000
        await stream_manager.broadcast(
            SignalPacket(
                event=SignalEvent.CACHE_HIT,
                source="warden_tower",
                destination="memory_vault",
                metadata={
                    "latency_ms": round(latency, 2),
                    "cost": 0.0,
                    "similarity": cached_result.get("similarity"),
                },
            )
        )
        return StructuredPulseResponse(
            query=req.prompt,
            response=cached_result["response"],
            destination="memory_vault",
            model="semantic-cache",
            latency_ms=round(latency, 2),
            cost_usd=0.0,
            cache_hit=True,
            evaluation_score=1.0,
        )

    await stream_manager.broadcast(
        SignalPacket(
            event=SignalEvent.CACHE_MISS,
            source="warden_tower",
            destination="memory_vault",
            metadata={"latency_ms": round((time.time() - start_time) * 1000, 2)},
        )
    )

    # Step 2: Smart route choice
    route_decision = smart_router.evaluate_route(req.prompt, user_tier=req.tier)
    destination = route_decision["destination"]
    target_model = route_decision["model"]
    await stream_manager.broadcast(
        SignalPacket(
            event=SignalEvent.ROUTING_SIGNAL,
            source="warden_tower",
            destination=destination,
            metadata={
                "model": target_model,
                "estimated_cost": route_decision["estimated_cost"],
                "reason": route_decision["reason"],
            },
        )
    )

    # Step 3: Model execution
    try:
        await stream_manager.broadcast(
            SignalPacket(
                event=SignalEvent.MODEL_EXECUTION,
                source=destination,
                destination=destination,
                metadata={"model": target_model},
            )
        )
        completion = await provider_manager.execute_completion(
            model=target_model,
            messages=[{"role": "user", "content": req.prompt}],
        )
    except Exception as exc:
        await stream_manager.broadcast(
            SignalPacket(
                event=SignalEvent.ERROR,
                source=destination,
                destination="warden_tower",
                metadata={"model": target_model, "error": str(exc)},
            )
        )
        raise

    # Step 4: Evaluation
    eval_result = await eval_engine.evaluate_faithfulness(req.prompt, completion["content"])
    await stream_manager.broadcast(
        SignalPacket(
            event=SignalEvent.EVALUATION,
            source=destination,
            destination="warden_tower",
            metadata={"score": eval_result["faithfulness_score"]},
        )
    )

    # Step 5: Populate cache and emit completion
    await cache_service.set(req.prompt, completion["content"])
    latency = (time.time() - start_time) * 1000
    await stream_manager.broadcast(
        SignalPacket(
            event=SignalEvent.COMPLETION,
            source=destination,
            destination="warden_tower",
            metadata={
                "latency_ms": round(latency, 2),
                "model": target_model,
                "score": eval_result["faithfulness_score"],
            },
        )
    )

    return StructuredPulseResponse(
        query=req.prompt,
        response=completion["content"],
        destination=destination,
        model=target_model,
        latency_ms=round(latency, 2),
        cost_usd=route_decision["estimated_cost"],
        cache_hit=False,
        evaluation_score=eval_result["faithfulness_score"],
    )
