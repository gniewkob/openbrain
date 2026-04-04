from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import get_config
from .exceptions import register_exception_handlers


def create_app(*, public_base_url: str, lifespan) -> FastAPI:
    config = get_config()
    servers = [{"url": public_base_url}] if public_base_url else []
    
    # Rate limiter with Redis backend if available, fallback to in-memory
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{config.rate_limit_per_minute}/minute"],
        storage_uri=config.redis.url
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
    if config.auth.public_mode:
        # In production, use specific allowed origins from config
        allowed_origins = config.cors.get_origins_list()
        if not allowed_origins or allowed_origins == ["http://localhost:*", "http://127.0.0.1:*"]:
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
