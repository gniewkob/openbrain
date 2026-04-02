from __future__ import annotations

from fastapi import FastAPI


def create_app(*, public_base_url: str, lifespan) -> FastAPI:
    servers = [{"url": public_base_url}] if public_base_url else []
    return FastAPI(
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
