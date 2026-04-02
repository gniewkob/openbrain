from __future__ import annotations

import re
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

from .telemetry import incr_metric, observe_metric

# Allowlist: UUID-like tokens only (alphanumeric + hyphens, 1-64 chars).
# Anything else is replaced with a server-generated UUID to prevent log injection.
REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9\-]{1,64}$")


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start_time
            incr_metric(f"http_requests_total_{status_code}")
            observe_metric("http_request_duration_seconds", duration)


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        raw = request.headers.get("X-Request-ID", "")
        req_id = raw if REQUEST_ID_RE.match(raw) else str(uuid.uuid4())
        structlog.contextvars.bind_contextvars(request_id=req_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
