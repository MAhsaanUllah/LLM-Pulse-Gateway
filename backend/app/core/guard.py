"""Request gates for the gateway: an optional bearer token and a per-client rate limit.

Both default to open. A gateway with no token is still usable for local development,
and the rate limit only bites once a client really overruns its window.
"""

import time
from collections import deque
from typing import Deque, Dict, Optional

from fastapi import HTTPException, Request, WebSocket

from config import settings


class RateLimiter:
    """Sliding one-minute window per client. In-process only — restarts reset it."""

    def __init__(self) -> None:
        self.hits: Dict[str, Deque[float]] = {}

    def retry_after(self, client: str, now: Optional[float] = None) -> Optional[float]:
        """None when the client may proceed, else seconds until a slot frees."""
        limit = settings.RATE_LIMIT_PER_MINUTE
        stamp = time.monotonic() if now is None else now
        hits = self.hits.setdefault(client, deque())
        while hits and stamp - hits[0] >= 60.0:
            hits.popleft()
        if limit > 0 and len(hits) >= limit:
            return round(60.0 - (stamp - hits[0]), 1)
        hits.append(stamp)
        return None


rate_limiter = RateLimiter()


def token_matches(presented: Optional[str]) -> bool:
    expected = settings.GATEWAY_TOKEN
    if not expected:
        return True
    return presented == f"Bearer {expected}"


def authorize_request(request: Request) -> None:
    """FastAPI dependency guarding every REST route on the gateway."""
    if not token_matches(request.headers.get("authorization")):
        raise HTTPException(status_code=401, detail="Missing or wrong gateway token")
    wait = rate_limiter.retry_after(request.client.host if request.client else "unknown")
    if wait is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many requests for this gateway",
            headers={"Retry-After": str(wait)},
        )


async def authorize_socket(websocket: WebSocket) -> bool:
    """The socket carries its credential in the query string, since a browser
    WebSocket cannot set an Authorization header."""
    if not settings.GATEWAY_TOKEN:
        return True
    if websocket.query_params.get("token") != settings.GATEWAY_TOKEN:
        await websocket.close(code=4401)
        return False
    return True
