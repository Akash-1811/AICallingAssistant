"""Optional shared-secret (X-API-Key header) gate for internal REST APIs.
WebSocket auth lives in app/api/websocket/realtime.py (first-message auth)."""

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_401_UNAUTHORIZED

from app.core.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_internal_api_key(api_key: str | None = Depends(api_key_header)) -> None:
    expected = settings.INTERNAL_API_KEY
    if not expected:
        return
    if not api_key or api_key != expected:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
