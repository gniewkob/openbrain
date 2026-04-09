"""
Combined ASGI app — Industrial Grade Wrapper v2.

This wrapper:
1. Forwards REST API, health, OpenAPI docs, and OAuth discovery to FastAPI (rest_app)
2. Redirects root (/) to /sse for ChatGPT convenience
3. Forwards everything else to FastMCP (authenticated when public exposure is enabled)
"""

import hmac
import logging

from .auth import INTERNAL_API_KEY, PUBLIC_EXPOSURE, _oidc
from .mcp_transport import STREAMABLE_HTTP_PATH, mcp as mcp_server
from .main import app as rest_app

_log = logging.getLogger("openbrain.combined")

# Base FastMCP app
mcp_app = mcp_server.streamable_http_app()

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


async def app(scope, receive, send):
    if scope["type"] == "http":
        path = scope["path"]

        # REST API, health, OpenAPI docs, and OAuth discovery (/.well-known/*)
        # FastAPI in main.py is the single authoritative handler for all of these.
        if (
            path in _REST_EXACT
            or path.startswith("/api")
            or path.startswith("/.well-known/")
        ):
            await rest_app(scope, receive, send)
            return

        # Root redirect to MCP streamable HTTP path (for ChatGPT MCP discovery)
        if path == "/":
            # 307 preserves the POST method
            await send(
                {
                    "type": "http.response.start",
                    "status": 307,
                    "headers": [(b"location", STREAMABLE_HTTP_PATH.encode("ascii"))],
                }
            )
            await send({"type": "http.response.body", "body": b""})
            return

    # Guard FastMCP transport with the same auth policy as the REST API.
    if PUBLIC_EXPOSURE and scope["type"] == "http":
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        authorized = False
        internal_key = headers.get(b"x-internal-key", b"").decode("latin-1")
        if (
            internal_key
            and INTERNAL_API_KEY
            and hmac.compare_digest(internal_key, INTERNAL_API_KEY)
        ):
            authorized = True
        if not authorized:
            auth_header = headers.get(b"authorization", b"").decode("latin-1")
            if auth_header.lower().startswith("bearer ") and _oidc:
                token = auth_header[7:].strip()
                try:
                    await _oidc.verify_token(token)
                    authorized = True
                except Exception as exc:
                    _log.warning(
                        "mcp_oidc_verification_failed", extra={"error": str(exc)}
                    )
        if not authorized:
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
