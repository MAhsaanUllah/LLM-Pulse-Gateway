from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class SignalStreamManager:
    """Manages active WebSocket connections and broadcasts real-time signal packets to the 3D Voxel canvas."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast_signal(self, event_type: str, source: str, destination: str, metadata: Dict[str, Any] = None):
        """Sends a real-time signal packet to all connected 3D canvas clients."""
        payload = {
            "event": event_type,
            "source": source,
            "destination": destination,
            "metadata": metadata or {},
        }
        message = json.dumps(payload)
        stale_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                stale_connections.append(connection)

        for connection in stale_connections:
            self.disconnect(connection)


stream_manager = SignalStreamManager()


@router.websocket("/ws/signals")
async def websocket_signals_endpoint(websocket: WebSocket):
    await stream_manager.connect(websocket)
    try:
        while True:
            # Keep-alive or handle incoming control messages from UI
            data = await websocket.receive_text()
            logger.debug(f"Received from 3D client: {data}")
    except WebSocketDisconnect:
        stream_manager.disconnect(websocket)
