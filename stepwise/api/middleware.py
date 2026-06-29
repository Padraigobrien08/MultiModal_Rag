"""API middleware — optional API-key auth and related request guards."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from stepwise.config import settings

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


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key (or Authorization: Bearer) when settings.api_key is set."""

    async def dispatch(self, request: Request, call_next):
        if not settings.api_key:
            return await call_next(request)
        if request.method == "OPTIONS" or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        provided = _extract_api_key(request)
        if provided != settings.api_key:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})

        return await call_next(request)
