from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.responses import PlainTextResponse

from .auth import require_auth
from .api.v1.health import healthz, readyz, health
from .config import get_config


def register_ops_routes(app: FastAPI, handlers) -> None:
    config = get_config()

    # Health endpoints moved to api.v1.health, registered here for backward
    # compatibility
    app.add_api_route("/healthz", healthz, methods=["GET"])
    app.add_api_route("/readyz", readyz, methods=["GET"], response_model=None)
    # /health requires auth in PUBLIC_MODE
    health_deps = [Depends(require_auth)] if config.auth.public_mode else []
    app.add_api_route(
        "/health",
        health,
        methods=["GET"],
        dependencies=health_deps,
        response_model=None,
    )
    app.add_api_route(
        "/api/diagnostics/metrics",
        handlers.diagnostics_metrics,
        methods=["GET"],
        dependencies=health_deps,
    )
    # /metrics requires auth in PUBLIC_MODE to prevent information leakage
    metrics_deps = [Depends(require_auth)] if config.auth.public_mode else []
    app.add_api_route(
        "/metrics",
        handlers.prometheus_metrics,
        methods=["GET"],
        response_class=PlainTextResponse,
        dependencies=metrics_deps,
    )
