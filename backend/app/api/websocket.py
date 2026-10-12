from enum import Enum
from typing import Any, Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
import logging

from app.core.guard import authorize_socket

logger = logging.getLogger(__name__)

router = APIRouter()


class SignalEvent(str, Enum):
    """Telemetry event types broadcast to the 3D voxel canvas."""

    CACHE_HIT = "CACHE_HIT"
    CACHE_MISS = "CACHE_MISS"
    ROUTING_SIGNAL = "ROUTING_SIGNAL"
    MODEL_EXECUTION = "MODEL_EXECUTION"
    EVALUATION = "EVALUATION"
    COMPLETION = "COMPLETION"
    ERROR = "ERROR"


class SignalPacket(BaseModel):
    """Real-time signal packet consumed by the voxel frontend."""

    event: SignalEvent
    source: str
    destination: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SignalStreamManager:
    """Tracks active WebSocket clients and broadcasts signal packets to the 3D canvas."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Total clients: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("WebSocket client disconnected. Total clients: %d", len(self.active_connections))

    async def broadcast(self, packet: SignalPacket) -> None:
        """Serialize the packet to JSON and fan it out to every connected client."""
        message = packet.model_dump_json()
        stale_connections: List[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                stale_connections.append(connection)
        for connection in stale_connections:
            self.disconnect(connection)


stream_manager = SignalStreamManager()


@router.websocket("/ws/signals")
async def websocket_signals_endpoint(websocket: WebSocket) -> None:
    if not await authorize_socket(websocket):
        return
    await stream_manager.connect(websocket)
    try:
        while True:
            # Keep-alive or handle incoming control messages from the UI
            data = await websocket.receive_text()
            logger.debug("Received from 3D client: %s", data)
    except WebSocketDisconnect:
        stream_manager.disconnect(websocket)
