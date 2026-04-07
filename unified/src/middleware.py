from __future__ import annotations

import json
import logging
import os
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


# ---------------------------------------------------------------------------
# Secret scanning middleware
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openai_api_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("github_token", re.compile(r"ghp_[A-Za-z0-9]{30,}")),
    ("slack_token", re.compile(r"xoxb-[A-Za-z0-9\-]+")),
    ("google_api_key", re.compile(r"AIza[A-Za-z0-9\-_]{35}")),
    ("jwt_token", re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
    ("pem_private_key", re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----")),
    ("auth_url", re.compile(r"https?://[^:@/\s]+:[^@/\s]+@\S+")),
    (
        "inline_credential",
        re.compile(r"(?:password|secret|api_key)\s*=\s*\S{6,}", re.IGNORECASE),
    ),
]

_WRITE_PATHS: frozenset[str] = frozenset(
    [
        "/api/v1/memory/write",
        "/api/v1/memory/write-many",
        "/api/v1/memory/bulk-upsert",
    ]
)

_PATCH_NON_ID_SEGMENTS: frozenset[str] = frozenset(
    [
        "write",
        "write-many",
        "bulk-upsert",
        "search",
        "export",
        "sync-check",
    ]
)

_scan_logger = logging.getLogger(__name__)


def _scan_string(value: str) -> tuple[bool, str | None]:
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            return True, name
    return False, None


def _scan_dict_values(data: dict) -> tuple[bool, str | None]:
    for value in data.values():
        if isinstance(value, str):
            found, name = _scan_string(value)
            if found:
                return True, name
        elif isinstance(value, dict):
            found, name = _scan_dict_values(value)
            if found:
                return True, name
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    found, name = _scan_dict_values(item)
                    if found:
                        return True, name
                elif isinstance(item, str):
                    found, name = _scan_string(item)
                    if found:
                        return True, name
    return False, None


def _scan_for_secrets(payload: dict) -> tuple[bool, str | None]:
    """Scan content and custom_fields for plaintext secrets.

    Returns (True, pattern_name) if a secret is detected, else (False, None).
    Never mutates the payload.
    """
    content = payload.get("content")
    if isinstance(content, str):
        found, name = _scan_string(content)
        if found:
            return True, name

    custom_fields = payload.get("custom_fields")
    if isinstance(custom_fields, dict):
        found, name = _scan_dict_values(custom_fields)
        if found:
            return True, name

    return False, None


def _is_write_path(path: str, method: str) -> bool:
    """Return True if this request path+method should be scanned."""
    if method == "POST" and path in _WRITE_PATHS:
        return True
    if method == "PATCH":
        parts = path.split("/")
        # Expect: ["", "api", "v1", "memory", "<id>"]
        if (
            len(parts) >= 5
            and parts[1] == "api"
            and parts[2] == "v1"
            and parts[3] == "memory"
            and parts[4]
            and parts[4] not in _PATCH_NON_ID_SEGMENTS
        ):
            return True
    return False


class SecretScanMiddleware(BaseHTTPMiddleware):
    """Block write requests containing plaintext secrets.

    Scans `content` and `custom_fields` (recursive) in POST/PATCH write
    endpoints. Returns 400 with ErrorDetail envelope on detection.

    Set DISABLE_SECRET_SCANNING=1 to bypass (for test environments).
    """

    async def dispatch(self, request, call_next):
        if os.environ.get("DISABLE_SECRET_SCANNING") == "1":
            _scan_logger.warning(
                "Secret scanning is DISABLED via DISABLE_SECRET_SCANNING=1"
            )
            return await call_next(request)

        method = request.method.upper()
        if not _is_write_path(request.url.path, method):
            return await call_next(request)

        body_bytes = await request.body()
        try:
            payload = json.loads(body_bytes)
        except (json.JSONDecodeError, ValueError):
            return await call_next(request)

        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            # Scan well-known fields first (content, custom_fields), then
            # fall back to full recursive scan to cover nested structures
            # like write-many's {"records": [...]} envelope.
            found, pattern_name = _scan_for_secrets(item)
            if not found:
                found, pattern_name = _scan_dict_values(item)
            if found:
                _scan_logger.warning(
                    "secret_scan_block path=%s pattern=%s",
                    request.url.path,
                    pattern_name,
                )
                incr_metric("secret_scan_blocks_total")
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "secret_detected",
                            "message": (
                                f"Plaintext secret detected ({pattern_name}). "
                                "Remove credentials before storing."
                            ),
                            "details": {"pattern": pattern_name},
                            "retryable": False,
                        }
                    },
                )

        return await call_next(request)
