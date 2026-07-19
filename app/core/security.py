"""Optional shared-secret auth for internal APIs and WebSocket."""

from typing import Optional

from fastapi import Depends, HTTPException
from starlette.websockets import WebSocket
from fastapi.security import APIKeyHeader
from starlette.status import HTTP_401_UNAUTHORIZED

from app.core.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_internal_api_key(api_key: Optional[str] = Depends(api_key_header)) -> None:
    expected = settings.INTERNAL_API_KEY
    if not expected:
        return
    if not api_key or api_key != expected:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def websocket_api_key_ok(websocket: WebSocket) -> bool:
    """Return True if connection is allowed. Caller should close websocket and return if False."""
    expected = settings.INTERNAL_API_KEY
    if not expected:
        return True
    header_key = websocket.headers.get("x-api-key")
    query_key = websocket.query_params.get("api_key")
    provided = header_key or query_key
    return bool(provided) and provided == expected
