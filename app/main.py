"""
Application entry point: assembles the FastAPI app from routers, and on startup
validates config, initializes the database, and warms up the RAG models.
Run with: uvicorn app.main:app
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.api.v1.auth  # noqa: F401 — register User model before create_all
from app.api.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.conversations import analytics_router
from app.api.v1.conversations import audio_router as conversations_audio_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.query import router as query_router
from app.api.websocket.realtime import router as realtime_router
from app.core.config import settings, validate_production_settings
from app.core.telemetry import setup_telemetry
from app.core.warmup import warm_rag_stack_sync
from app.live.conversation_manager import (
    conversation_manager,
)
from app.rag.answer_cache import close_answer_cache
from app.storage.call_store import close_database, init_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_production_settings()
    setup_telemetry()
    await init_database()
    if settings.RAG_WARMUP_ON_STARTUP:
        await asyncio.to_thread(warm_rag_stack_sync)
    yield
    await conversation_manager.close()
    close_answer_cache()
    await close_database()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

app.include_router(auth_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(conversations_audio_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(realtime_router, prefix="/ws")
app.include_router(health_router, prefix="/health")

@app.get("/")
def root():
    return {"message": "AI Sales Assistant API", "docs": "/docs"}


@app.get("/health")
def health_legacy():
    """Backward-compatible liveness endpoint."""
    return {"status": "ok"}
