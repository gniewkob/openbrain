"""
Combined ASGI app — Industrial Grade Wrapper v2.

This wrapper:
1. Forwards REST API, health, OpenAPI docs, and OAuth discovery to FastAPI (rest_app)
2. Redirects root (/) to configured streamable path for ChatGPT convenience
3. Forwards everything else to FastMCP (authenticated when public exposure is enabled)
"""

import hmac
import logging

from .auth import INTERNAL_API_KEY, PUBLIC_EXPOSURE, _oidc
from . import mcp_transport
from .main import app as rest_app

_log = logging.getLogger("openbrain.combined")

# Base FastMCP app
mcp_app = mcp_transport.mcp.streamable_http_app()

# Exact paths routed to the FastAPI REST application.
_REST_EXACT = {
    "/health",
    "/healthz",
    "/readyz",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _is_rest_path(path: str) -> bool:
    return (
        path in _REST_EXACT
        or path.startswith("/api")
        or path.startswith("/.well-known/")
    )


async def _send_root_redirect(send) -> None:
    streamable_http_path = mcp_transport.STREAMABLE_HTTP_PATH
    if streamable_http_path == "/":
        _log.error(
            "invalid_streamable_http_path",
            extra={"streamable_http_path": streamable_http_path},
        )
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"detail":"Invalid MCP streamable transport path configuration"}',
            }
        )
        return
    await send(
        {
            "type": "http.response.start",
            "status": 307,
            "headers": [(b"location", streamable_http_path.encode("ascii"))],
        }
    )
    await send({"type": "http.response.body", "body": b""})


async def _authorize_mcp(scope) -> bool:
    """Return True if the request is authorized to reach FastMCP."""
    headers = {k.lower(): v for k, v in scope.get("headers", [])}
    internal_key = headers.get(b"x-internal-key", b"").decode("latin-1")
    if (
        internal_key
        and INTERNAL_API_KEY
        and hmac.compare_digest(internal_key, INTERNAL_API_KEY)
    ):
        return True
    auth_header = headers.get(b"authorization", b"").decode("latin-1")
    if auth_header.lower().startswith("bearer ") and _oidc:
        token = auth_header[7:].strip()
        try:
            await _oidc.verify_token(token)
            return True
        except Exception as exc:
            _log.warning("mcp_oidc_verification_failed", extra={"error": str(exc)})
    return False


async def app(scope, receive, send):
    if scope["type"] == "http":
        path = scope["path"]

        if _is_rest_path(path):
            await rest_app(scope, receive, send)
            return

        if path == "/":
            await _send_root_redirect(send)
            return

    if PUBLIC_EXPOSURE and scope["type"] == "http":
        if not await _authorize_mcp(scope):
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {"type": "http.response.body", "body": b'{"detail":"Unauthorized"}'}
            )
            return

    # Default: Forward to FastMCP (handles MCP streamable HTTP and protocol paths)
    await mcp_app(scope, receive, send)
