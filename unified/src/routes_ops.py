from __future__ import annotations

import os

from fastapi import Depends, FastAPI
from fastapi.responses import PlainTextResponse

from .auth import require_auth

PUBLIC_MODE = os.environ.get("PUBLIC_MODE", "").lower() == "true"


def register_ops_routes(app: FastAPI, handlers) -> None:
    app.add_api_route("/healthz", handlers.healthz, methods=["GET"])
    app.add_api_route("/readyz", handlers.readyz, methods=["GET"])
    # /health requires auth in PUBLIC_MODE
    health_deps = [Depends(require_auth)] if PUBLIC_MODE else []
    app.add_api_route("/health", handlers.health, methods=["GET"], dependencies=health_deps)
    app.add_api_route(
        "/api/diagnostics/metrics",
        handlers.diagnostics_metrics,
        methods=["GET"],
        dependencies=health_deps,
    )
    # /metrics requires auth in PUBLIC_MODE to prevent information leakage
    metrics_deps = [Depends(require_auth)] if PUBLIC_MODE else []
    app.add_api_route(
        "/metrics",
        handlers.prometheus_metrics,
        methods=["GET"],
        response_class=PlainTextResponse,
        dependencies=metrics_deps,
    )
