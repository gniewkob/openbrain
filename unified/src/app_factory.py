from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_config
from .exceptions import register_exception_handlers

_ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "X-Request-ID",
    "X-Internal-Key",
]

_EXPOSE_HEADERS = ["X-Request-ID"]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Add security headers to the response."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
        # HSTS only in production (requires HTTPS)
        if get_config().auth.public_mode:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


def create_app(*, public_base_url: str, lifespan) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        public_base_url: Public URL for OpenAPI server configuration
        lifespan: Lifespan context manager for startup/shutdown events

    Returns:
        Configured FastAPI application instance
    """
    config = get_config()
    servers = [{"url": public_base_url}] if public_base_url else []

    # Hide docs in public/production mode (information disclosure)
    is_public = config.auth.public_mode or bool(config.auth.public_base_url)

    # Rate limiter with Redis backend if available, fallback to in-memory
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{config.rate_limit_per_minute}/minute"],
        storage_uri=config.redis.url,
    )

    app = FastAPI(
        title="OpenBrain Unified Memory Service",
        version="2.0.0",
        description=(
            "Unified memory store with domain-aware governance. "
            "Corporate: append-only versioning + audit trail. "
            "Build/Personal: mutable + deletable."
        ),
        servers=servers or None,
        docs_url=None if is_public else "/docs",
        openapi_url=None if is_public else "/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )

    # Add rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Configure CORS — explicit allowed headers, never wildcard
    if config.auth.public_mode:
        allowed_origins = config.cors.get_origins_list()
        if not allowed_origins or allowed_origins == [
            "http://localhost:*",
            "http://127.0.0.1:*",
        ]:
            allowed_origins = [public_base_url] if public_base_url else []
    else:
        allowed_origins = ["http://localhost:*", "http://127.0.0.1:*"]

    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=_ALLOWED_HEADERS,
            expose_headers=_EXPOSE_HEADERS,
            max_age=600,
        )

    # Security headers on every response (added after CORS — runs first in ASGI stack)
    app.add_middleware(SecurityHeadersMiddleware)

    # Register centralized exception handlers
    register_exception_handlers(app)

    return app
