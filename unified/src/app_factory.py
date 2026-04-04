from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .exceptions import register_exception_handlers


def create_app(*, public_base_url: str, lifespan) -> FastAPI:
    servers = [{"url": public_base_url}] if public_base_url else []
    
    # Rate limiter with Redis backend if available, fallback to in-memory
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["100/minute"],
        storage_uri=os.environ.get("REDIS_URL", "memory://")
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
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    
    # Add rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Configure CORS - in production, restrict to specific origins
    public_mode = os.environ.get("PUBLIC_MODE", "").lower() == "true"
    if public_mode:
        # In production, use specific allowed origins from env
        allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
        allowed_origins = [o.strip() for o in allowed_origins if o.strip()]
        if not allowed_origins:
            allowed_origins = [public_base_url] if public_base_url else []
    else:
        # In development, allow localhost
        allowed_origins = ["http://localhost:*", "http://127.0.0.1:*"]
    
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )
    
    # Register centralized exception handlers
    register_exception_handlers(app)
    
    return app
