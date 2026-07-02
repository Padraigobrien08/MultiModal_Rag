"""API middleware — request IDs, optional API-key auth, and related guards."""

import hmac
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from stepwise.config import settings

log = logging.getLogger(__name__)

# Paths that never require an API key (even when API_KEY is configured).
_PUBLIC_PATHS = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})


def _extract_api_key(request: Request) -> str | None:
    header = request.headers.get("X-API-Key")
    if header:
        return header.strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to each request and echo it on the response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key (or Authorization: Bearer) when settings.api_key is set."""

    async def dispatch(self, request: Request, call_next):
        if not settings.api_key:
            return await call_next(request)
        if request.method == "OPTIONS" or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        provided = _extract_api_key(request)
        # Constant-time comparison to avoid leaking the key via timing.
        if provided is None or not hmac.compare_digest(provided, settings.api_key):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

        return await call_next(request)
