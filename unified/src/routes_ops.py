from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse


def register_ops_routes(app: FastAPI, handlers) -> None:
    app.add_api_route("/healthz", handlers.healthz, methods=["GET"])
    app.add_api_route("/readyz", handlers.readyz, methods=["GET"])
    app.add_api_route("/health", handlers.health, methods=["GET"])
    app.add_api_route(
        "/api/diagnostics/metrics",
        handlers.diagnostics_metrics,
        methods=["GET"],
    )
    app.add_api_route(
        "/metrics",
        handlers.prometheus_metrics,
        methods=["GET"],
        response_class=PlainTextResponse,
    )
