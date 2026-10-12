import os
import sys
from pathlib import Path

# Ensure backend root is always in sys.path
BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from app.api.gateway import router as gateway_router
from app.api.websocket import router as websocket_router

app = FastAPI(
    title=settings.APP_NAME,
    description="LLM Pulse Gateway - AI Platform Gateway with Real-Time 3D Voxel Telemetry",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Subsystem Routers
app.include_router(gateway_router, prefix="/api", tags=["Gateway"])
app.include_router(websocket_router, tags=["WebSocket Telemetry"])


@app.get("/health")
def health_check():
    return {"status": "ok", "app": settings.APP_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
