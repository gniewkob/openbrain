"""Utilities shared by MCP HTTP transport internals."""

from __future__ import annotations

import functools
from typing import Any


def http_obsidian_disabled_reason() -> str:
    """Return standard disabled reason for HTTP Obsidian tool surface."""
    return (
        "HTTP Obsidian tools are disabled by default. "
        "Set ENABLE_HTTP_OBSIDIAN_TOOLS=1 before starting transport."
    )


def make_tool_guard(logger):
    """Wrap MCP tool functions with consistent error framing."""

    def _decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                logger.error("mcp_tool_error", tool=func.__name__, error=str(exc))
                raise ValueError(f"Tool execution failed: {str(exc)}") from exc

        return wrapper

    return _decorator


def extract_record_from_write_response(
    payload: dict[str, Any], to_legacy_record
) -> dict[str, Any]:
    """Extract and normalize write response payload shape."""
    record = payload.get("record")
    if not isinstance(record, dict):
        raise ValueError(f"Write response missing record payload: {payload}")
    return to_legacy_record(record)


def redact_logged_payload(payload: Any, sensitive_fields: set[str]) -> Any:
    """Redact sensitive payload fields recursively before logging."""
    if isinstance(payload, dict):
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            if key in sensitive_fields:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_logged_payload(value, sensitive_fields)
        return redacted
    if isinstance(payload, list):
        return [redact_logged_payload(item, sensitive_fields) for item in payload]
    return payload
