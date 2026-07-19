"""Liveness and readiness probes for orchestration and load balancers."""

from typing import Any, Dict

from fastapi import APIRouter
from qdrant_client import QdrantClient

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/live")
def live() -> Dict[str, str]:
    """Process is up (do not check dependencies)."""
    return {"status": "ok"}


@router.get("/ready")
def ready() -> Dict[str, Any]:
    """
    Dependency checks for traffic routing.
    Fails if Qdrant is unreachable (required for RAG).
    """
    checks: Dict[str, Any] = {"qdrant": "unknown", "redis": "skipped"}

    try:
        client = QdrantClient(settings.QDRANT_URL, timeout=5)
        client.get_collections()
        checks["qdrant"] = "ok"
    except Exception as e:
        logger.warning("Readiness: Qdrant check failed: %s", e)
        checks["qdrant"] = f"error: {type(e).__name__}"
        return {"status": "not_ready", "checks": checks}

    if settings.REDIS_URL:
        try:
            import redis

            r = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=3)
            r.ping()
            checks["redis"] = "ok"
        except Exception as e:
            logger.warning("Readiness: Redis check failed: %s", e)
            checks["redis"] = f"error: {type(e).__name__}"
            return {"status": "not_ready", "checks": checks}

    return {"status": "ready", "checks": checks}
