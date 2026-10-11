from fastapi import APIRouter
import time
from app.features.parser import GatewayRequest, StructuredPulseResponse
from app.core.cache import cache_service
from app.core.router import smart_router
from app.core.providers import provider_manager
from app.features.evals import eval_engine
from app.api.websocket import stream_manager

router = APIRouter()


@router.post("/gateway/chat", response_model=StructuredPulseResponse)
async def process_gateway_request(req: GatewayRequest):
    start_time = time.time()

    # 1. Check Semantic Cache
    cached_result = await cache_service.get(req.prompt)
    if cached_result:
        latency = (time.time() - start_time) * 1000
        await stream_manager.broadcast_signal(
            event_type="CACHE_HIT",
            source="warden_tower",
            destination="memory_vault",
            metadata={"latency_ms": latency, "cost": 0.0},
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

    # 2. Cache Miss -> Route Request
    route_decision = smart_router.evaluate_route(req.prompt, user_tier=req.tier)
    destination = route_decision["destination"]
    target_model = route_decision["model"]

    # Broadcast routing signal to 3D Canvas
    await stream_manager.broadcast_signal(
        event_type="ROUTING_SIGNAL",
        source="warden_tower",
        destination=destination,
        metadata={"model": target_model, "estimated_cost": route_decision["estimated_cost"]},
    )

    # 3. Call Provider (LiteLLM / Local SLM / Cloud)
    completion = await provider_manager.execute_completion(
        model=target_model,
        messages=[{"role": "user", "content": req.prompt}],
    )

    # 4. Evaluation
    eval_result = await eval_engine.evaluate_faithfulness(req.prompt, completion["content"])

    # 5. Populate Cache
    await cache_service.set(req.prompt, completion["content"])

    latency = (time.time() - start_time) * 1000

    # Broadcast completion signal
    await stream_manager.broadcast_signal(
        event_type="COMPLETION_COMPLETED",
        source=destination,
        destination="warden_tower",
        metadata={"latency_ms": latency, "score": eval_result["faithfulness_score"]},
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
