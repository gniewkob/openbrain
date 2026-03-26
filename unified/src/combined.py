"""
Combined ASGI app — Industrial Grade Wrapper v2.

This wrapper:
1. Handles OAuth discovery at /.well-known
2. Forwards REST API calls at /api
3. Redirects root (/) to /sse for ChatGPT convenience
4. Forwards everything else to FastMCP
"""
import os
import json
from .mcp_transport import mcp as mcp_server
from .main import app as rest_app

# Base FastMCP app
mcp_app = mcp_server.streamable_http_app()

async def app(scope, receive, send):
    if scope["type"] == "http":
        path = scope["path"]
        
        # 1. OAuth Discovery
        if path == "/.well-known/oauth-protected-resource":
            public_base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:7010").rstrip("/")
            oidc_issuer = os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")
            content = json.dumps({"resource": public_base, "authorization_servers": [oidc_issuer]}).encode("utf-8")
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": content})
            return

        if path == "/.well-known/oauth-authorization-server":
            oidc_issuer = os.environ.get("OIDC_ISSUER_URL", "").rstrip("/")
            content = json.dumps({
                "issuer": oidc_issuer,
                "authorization_endpoint": f"{oidc_issuer}/authorize",
                "token_endpoint": f"{oidc_issuer}/oauth/token",
                "registration_endpoint": f"{oidc_issuer}/oidc/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
            }).encode("utf-8")
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": content})
            return

        # 2. REST API and health
        if path == "/health" or path.startswith("/api"):
            await rest_app(scope, receive, send)
            return

        # 3. Root Redirect to /sse (for ChatGPT)
        if path == "/":
            # 307 preserves the POST method
            await send({
                "type": "http.response.start",
                "status": 307,
                "headers": [(b"location", b"/sse")]
            })
            await send({"type": "http.response.body", "body": b""})
            return

    # 4. Default: Forward to FastMCP
    await mcp_app(scope, receive, send)
