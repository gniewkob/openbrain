"""
Combined ASGI app — Industrial Grade Wrapper v2.

This wrapper:
1. Forwards REST API, health, OpenAPI docs, and OAuth discovery to FastAPI (rest_app)
2. Redirects root (/) to /sse for ChatGPT convenience
3. Forwards everything else to FastMCP
"""
from .mcp_transport import mcp as mcp_server
from .main import app as rest_app

# Base FastMCP app
mcp_app = mcp_server.streamable_http_app()

# Exact paths routed to the FastAPI REST application.
_REST_EXACT = {
    "/health", "/healthz", "/readyz", "/metrics",
    "/docs", "/openapi.json", "/redoc",
}


async def app(scope, receive, send):
    if scope["type"] == "http":
        path = scope["path"]

        # REST API, health, OpenAPI docs, and OAuth discovery (/.well-known/*)
        # FastAPI in main.py is the single authoritative handler for all of these.
        if path in _REST_EXACT or path.startswith("/api") or path.startswith("/.well-known/"):
            await rest_app(scope, receive, send)
            return

        # Root redirect to /sse (for ChatGPT MCP discovery)
        if path == "/":
            # 307 preserves the POST method
            await send({
                "type": "http.response.start",
                "status": 307,
                "headers": [(b"location", b"/sse")],
            })
            await send({"type": "http.response.body", "body": b""})
            return

    # Default: Forward to FastMCP (handles /sse and all MCP protocol paths)
    await mcp_app(scope, receive, send)
