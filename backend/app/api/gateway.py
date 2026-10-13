from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
import json
import time
from typing import List, Optional

from app.api.websocket import SignalEvent, SignalPacket, stream_manager
from app.core.cache import cache_service
from app.core.guard import authorize_request
from app.core.providers import provider_manager
from app.core.router import smart_router
from app.core.usage import usage_ledger
from app.features.evals import eval_engine
from app.features.parser import (
    CacheClearResponse,
    GatewayRequest,
    MAX_HISTORY_TURNS,
    ModelsResponse,
    StructuredPulseResponse,
    UsageSummaryResponse,
)

router = APIRouter(dependencies=[Depends(authorize_request)])

# Kept in sync with the block route below by tests/test_stream.py rather than a shared
# trail object: two routes is cheaper to read than an abstraction that only two use.

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


@router.get("/gateway/metrics")
async def get_prometheus_metrics() -> StreamingResponse:
    """The ledger as Prometheus gauges, so a scraper sees what /api/gateway/usage shows.

    Every number is read from the same SQLite rows the usage endpoint reports; there is
    no second counting path that could disagree with the ledger.
    """
    totals = usage_ledger.totals()
    gauges = [
        ("gateway_requests_total", "Requests served since the ledger was created.", totals["requests"]),
        ("gateway_tokens_used_total", "Provider-reported tokens spent.", totals["tokens_used"]),
        ("gateway_cache_hits_total", "Answers served from the semantic cache.", totals["cache_hits"]),
        ("gateway_avg_latency_ms", "Mean wall-clock answer latency.", totals["avg_latency_ms"]),
        ("gateway_estimated_cost_usd", "Router-side cost estimate summed over all answers.", totals["estimated_cost_usd"]),
    ]
    lines = []
    for name, help_text, value in gauges:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value}")
    return StreamingResponse(iter(["\n".join(lines) + "\n"]), media_type="text/plain; version=0.0.4")


@router.post("/gateway/cache/clear", response_model=CacheClearResponse)
async def clear_semantic_cache() -> CacheClearResponse:
    """Drop every stored answer so the next prompt is genuinely re-asked."""
    return CacheClearResponse(cache_backend=await cache_service.clear())


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

    # Step 1: Semantic cache check. Skipped mid-conversation: the cache matches on the
    # words of the last prompt alone, and "and in one word?" means something different
    # in every conversation.
    history = req.history[-MAX_HISTORY_TURNS:]
    in_conversation = bool(history)
    cached_result = None if in_conversation else await cache_service.get(req.prompt)
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

    if not in_conversation:
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
            "turns": len(history) + 1,
        },
    )

    # Step 3: Model execution
    try:
        await emit(SignalEvent.MODEL_EXECUTION, destination, destination, {"model": target_model})
        completion = await provider_manager.execute_completion(
            model=target_model,
            messages=[
                {"role": "system", "content": ANSWER_STYLE},
                *(turn.model_dump() for turn in history),
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
    # A truncated answer is half a sentence, a stand-in is the prompt echoed by code, and
    # an in-conversation answer only means something with its context — caching any of
    # those would replay it to a stranger as if a model had answered on its own.
    if not truncated and not in_conversation and completion["status"] != "simulated":
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
    key_source = (completion.get("metadata") or {}).get("key_source")
    ledger(
        destination,
        completion["model_used"],
        completion["status"],
        False,
        completion["tokens_used"],
        estimated_cost,
        key_source,
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
        key_source=key_source,
        truncated=truncated,
        signals=[packet.model_dump() for packet in emitted],
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/gateway/chat/stream")
async def process_gateway_stream(req: GatewayRequest) -> StreamingResponse:
    """The same lifecycle as POST /gateway/chat, but the answer arrives as it is written.

    A frame is `event: signal | delta | done` with a JSON data line, so the canvas can
    keep animating and the ledger still sees exactly one request.
    """
    return StreamingResponse(_streamed_gateway(req), media_type="text/event-stream")


async def _streamed_gateway(req: GatewayRequest):
    start_time = time.time()

    def elapsed_ms() -> float:
        return round((time.time() - start_time) * 1000, 2)

    async def signal(event: SignalEvent, source: str, destination: str, metadata: dict) -> str:
        packet = SignalPacket(event=event, source=source, destination=destination, metadata=metadata)
        await stream_manager.broadcast(packet)
        return _sse("signal", {"event": packet.event.value, **packet.metadata})

    history = req.history[-MAX_HISTORY_TURNS:]
    in_conversation = bool(history)

    # A cached answer needs no model, so it arrives as one piece and a done frame.
    cached_result = None if in_conversation else await cache_service.get(req.prompt)
    if cached_result:
        cache_metadata = cached_result.get("metadata") or {}
        model = cache_metadata.get("model", "semantic-cache")
        yield await signal(
            SignalEvent.CACHE_HIT,
            "warden_tower",
            "memory_vault",
            {"latency_ms": elapsed_ms(), "cost": 0.0, "similarity": cached_result.get("similarity"), "model": model},
        )
        usage_ledger.record(
            route="memory_vault", model=model, status="cached", cache_hit=True, tokens_used=0,
            latency_ms=elapsed_ms(), estimated_cost_usd=0.0, key_source=None,
        )
        answer = cached_result["response"]
        yield _sse("delta", {"text": answer})
        yield _sse("done", {
            "response": answer,
            "destination": "memory_vault",
            "model": model,
            "provider_used": cache_metadata.get("provider", "memory_vault"),
            "status": "cached",
            "tokens_used": 0,
            "latency_ms": elapsed_ms(),
            "cost_usd": 0.0,
            "key_source": None,
            "truncated": False,
        })
        return

    yield await signal(SignalEvent.CACHE_MISS, "warden_tower", "memory_vault", {"latency_ms": elapsed_ms()})

    route_decision = smart_router.evaluate_route(req.prompt, user_tier=req.tier)
    destination = route_decision["destination"]
    target_model = route_decision["model"]
    yield await signal(
        SignalEvent.ROUTING_SIGNAL,
        "warden_tower",
        destination,
        {
            "model": target_model,
            "estimated_cost": route_decision["estimated_cost"],
            "reason": route_decision["reason"],
            "complexity": route_decision["complexity_metrics"],
            "turns": len(history) + 1,
        },
    )

    yield await signal(SignalEvent.MODEL_EXECUTION, destination, destination, {"model": target_model})
    messages = [
        {"role": "system", "content": ANSWER_STYLE},
        *(turn.model_dump() for turn in history),
        {"role": "user", "content": req.prompt},
    ]

    pieces: List[str] = []
    final: dict = {}
    try:
        async for piece in provider_manager.stream_completion(target_model, messages, byok=req.byok):
            if piece["kind"] == "delta":
                pieces.append(piece["text"])
                yield _sse("delta", {"text": piece["text"]})
            else:
                final = piece
    except Exception as exc:
        yield await signal(SignalEvent.ERROR, destination, "warden_tower", {"model": target_model, "error": str(exc)})
        usage_ledger.record(
            route=destination, model=target_model, status="error", cache_hit=False, tokens_used=0,
            latency_ms=elapsed_ms(), estimated_cost_usd=0.0, key_source=None,
        )
        yield _sse("error", {"detail": str(exc)})
        return

    latency_ms = elapsed_ms()
    content = final.get("content", "".join(pieces))
    truncated = bool(final.get("truncated"))
    status = final.get("status", "success")
    eval_result = await eval_engine.evaluate(content, status)
    yield await signal(
        SignalEvent.EVALUATION,
        destination,
        "warden_tower",
        {"passed": eval_result["passed"], "checks": eval_result["checks"], "status": status},
    )

    # Same three refusal rules as the block route: half an answer, an echo, or an
    # answer that only means something with its conversation attached.
    if not truncated and not in_conversation and status != "simulated":
        await cache_service.set(
            req.prompt,
            content,
            {
                "model": final.get("model_used"),
                "provider": final.get("provider"),
                "status": status,
                "tokens": final.get("tokens_used", 0),
            },
        )

    key_source = (final.get("metadata") or {}).get("key_source")
    estimated_cost = 0.0 if status == "simulated" else route_decision["estimated_cost"]
    usage_ledger.record(
        route=destination,
        model=final.get("model_used", target_model),
        status=status,
        cache_hit=False,
        tokens_used=final.get("tokens_used", 0),
        latency_ms=latency_ms,
        estimated_cost_usd=estimated_cost,
        key_source=key_source,
    )

    yield await signal(
        SignalEvent.COMPLETION,
        destination,
        "warden_tower",
        {
            "latency_ms": latency_ms,
            "model": final.get("model_used", target_model),
            "passed": eval_result["passed"],
            "tokens": final.get("tokens_used", 0),
            "status": status,
            "truncated": truncated,
        },
    )
    yield _sse("done", {
        "response": content,
        "destination": destination,
        "model": final.get("model_used", target_model),
        "provider_used": final.get("provider", ""),
        "status": status,
        "tokens_used": final.get("tokens_used", 0),
        "latency_ms": latency_ms,
        "cost_usd": estimated_cost,
        "key_source": key_source,
        "truncated": truncated,
    })
