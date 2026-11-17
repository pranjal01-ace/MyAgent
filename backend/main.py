"""
Main Application Entrypoint.

Configures FastAPI instance, CORS middleware, global exception handlers,
and registers all domain routers (conversations, memories, voice, health, websocket).
"""

import logging
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.core.database import init_db
from backend.common.exceptions import AppException
from backend.common.exception_handlers import app_exception_handler, generic_exception_handler
from backend.conversations import conversations_router
from backend.memories import memories_router, memory_alias_router
from backend.voice import voice_router
from backend.tools.router import router as tools_router
from backend.vision.router import router as gesture_router
from backend.api import health, websocket

# Setup application logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ace.main")

# Instantiate FastAPI application
app = FastAPI(
    title="Portgas D. Ace AI Desktop Companion API",
    version="2.0.0",
    description="Modular Domain-Driven Backend API powering Ace AI avatar companion"
)

# Register custom application exception handlers
app.add_exception_handler(AppException, app_exception_handler)

# CORS Middleware setup to allow desktop UI & web client communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register domain routers under /api prefix
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(conversations_router, prefix="/api")
app.include_router(memories_router, prefix="/api")
app.include_router(memory_alias_router, prefix="/api")
app.include_router(voice_router, prefix="/api")
app.include_router(tools_router, prefix="/api")
app.include_router(gesture_router, prefix="/api")
app.include_router(websocket.router, tags=["WebSocket"])


@app.on_event("startup")
async def startup_event():
    """Startup lifecycle hook: initializes database schema and pre-warms Ollama model."""
    from backend.llm.ollama_client import ollama_client
    
    logger.info("Initializing database tables and vector extensions...")
    init_db()

    # Initialize Tool & Action registry
    from backend.tools.initialize import initialize_tools
    from backend.tools.registry import tool_registry
    initialize_tools(tool_registry)
    
    # Pre-warm Ollama model in background so first prompt has zero cold-start latency
    asyncio.create_task(ollama_client.warmup())

    # Auto-start gesture recognition if configured
    if getattr(settings, "GESTURE_ENABLED", False):
        from backend.vision.gesture_manager import gesture_manager
        logger.info("Auto-starting gesture recognition subsystem (GESTURE_ENABLED=True)...")
        loop = asyncio.get_running_loop()
        gesture_manager.start(event_loop=loop)
    
    logger.info(
        f"🔥 Portgas D. Ace AI Backend Server running on http://{settings.API_HOST}:{settings.API_PORT}"
    )


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown hook: ensures clean release of camera hardware and worker thread termination."""
    logger.info("Application shutting down: releasing vision hardware and camera...")
    from backend.vision.gesture_manager import gesture_manager
    gesture_manager.stop()


@app.get("/", summary="Root Health Check")
async def root():
    """Root status endpoint returning service health and docs URL."""
    return {
        "message": "🔥 Portgas D. Ace Desktop AI Companion Backend is active!",
        "docs_url": f"http://{settings.API_HOST}:{settings.API_PORT}/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.API_HOST, port=settings.API_PORT, reload=True)
