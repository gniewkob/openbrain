"""
OpenBrain MCP HTTP Gateway — HTTP transport with OAuth 2.1 for ChatGPT / Claude Desktop.

Runs on port 7011 (mapped externally by Docker / ngrok).
OAuth flow:
  1. ChatGPT registers itself via Dynamic Client Registration (/register).
  2. ChatGPT redirects the user to /authorize → SDK validates → provider.authorize()
     returns a redirect to /consent?<encoded state>.
  3. User enters INTERNAL_API_KEY on /consent; on success we redirect to
     redirect_uri?code=<auth_code>&state=<state>.
  4. ChatGPT exchanges the code at /token for an access token.
  5. All MCP calls carry Authorization: Bearer <access_token>.

Token persistence:
  Tokens are stored in Redis so they survive container restarts.
  Clients reconnect without re-authenticating.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode
from urllib.parse import urlparse

import redis.asyncio as aioredis
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
)
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse


class _OpenRedirectClient(OAuthClientInformationFull):
    """
    OAuthClientInformationFull subclass that accepts any HTTPS redirect URI.
    Used for auto-registered clients (those that skip DCR, e.g. ChatGPT).
    Security is enforced on the consent page instead.
    """

    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is None:
            raise ValueError("redirect_uri required for auto-registered clients")
        uri_str = str(redirect_uri)
        if not uri_str.startswith("https://"):
            raise ValueError(f"Only HTTPS redirect URIs allowed, got: {uri_str}")
        return redirect_uri


from fastmcp.server.auth.auth import OAuthProvider

# Re-use the shared FastMCP instance with all brain_* tools
from .main import mcp

INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "").strip()
PUBLIC_BASE_URL_RAW: str = os.environ.get("PUBLIC_BASE_URL", "")
REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/1")

ACCESS_TOKEN_TTL = 30 * 24 * 3600  # 30 days for personal use
AUTH_CODE_TTL = 600  # 10 min

# Redis key prefixes
_PFX_CLIENT = "mcp:client:"
_PFX_PENDING = "mcp:pending:"
_PFX_CODE = "mcp:code:"
_PFX_AT = "mcp:at:"
_PFX_RT = "mcp:rt:"


def _normalize_public_base_url(value: str | None) -> str:
    normalized = (value or "").strip().rstrip("/")
    if any(ch.isspace() for ch in normalized):
        raise ValueError("PUBLIC_BASE_URL must not include whitespace")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("PUBLIC_BASE_URL must be a valid http(s) URL")
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and host not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(
            "PUBLIC_BASE_URL must use https outside localhost development"
        )
    if parsed.path not in {"", "/"}:
        raise ValueError("PUBLIC_BASE_URL must not include path")
    if parsed.query or parsed.fragment:
        raise ValueError("PUBLIC_BASE_URL must not include query params or fragment")
    return normalized


def _normalize_mcp_http_port(value: str | None) -> int:
    try:
        port = int((value or "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("MCP_HTTP_PORT must be an integer") from exc
    if port < 1 or port > 65535:
        raise ValueError("MCP_HTTP_PORT must be in range 1..65535")
    return port


def _dumps(obj) -> str:
    """Serialize a pydantic model or dict to JSON string."""
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(mode="json"))
    return json.dumps(obj)


class SimpleKeyOAuthProvider(OAuthProvider):
    """
    OAuth 2.1 provider secured by INTERNAL_API_KEY with Redis-backed persistence.

    Tokens survive container restarts — clients reconnect without re-authenticating.
    The user enters the key once on /consent; subsequent reconnects are automatic.
    """

    def __init__(self, base_url: str, redis: aioredis.Redis) -> None:
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["mcp"],
                default_scopes=["mcp"],
            ),
            revocation_options=RevocationOptions(enabled=True),
        )
        self._base_url = base_url
        self._r = redis

    # ── Client registry ───────────────────────────────────────────────────────

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        raw = await self._r.get(f"{_PFX_CLIENT}{client_id}")
        if raw:
            return OAuthClientInformationFull(**json.loads(raw))
        # Auto-register any client that skips DCR (e.g. ChatGPT).
        auto = _OpenRedirectClient(
            client_id=client_id,
            client_secret=None,
            redirect_uris=[AnyUrl("https://placeholder.invalid")],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
            scope="mcp",
        )
        await self._r.set(f"{_PFX_CLIENT}{client_id}", _dumps(auto))
        return auto

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await self._r.set(f"{_PFX_CLIENT}{client_info.client_id}", _dumps(client_info))

    # ── Authorization redirect ────────────────────────────────────────────────

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        pending_id = secrets.token_urlsafe(16)
        payload = {
            "client_id": client.client_id,
            "params": params.model_dump(mode="json"),
            "expires_at": time.time() + AUTH_CODE_TTL,
        }
        await self._r.setex(
            f"{_PFX_PENDING}{pending_id}", AUTH_CODE_TTL, json.dumps(payload)
        )
        return f"{self._base_url}/consent?pending_id={pending_id}"

    # ── Consent page ──────────────────────────────────────────────────────────

    async def consent_handler(
        self, request: Request
    ) -> HTMLResponse | RedirectResponse:
        pending_id = request.query_params.get("pending_id", "")
        raw = await self._r.get(f"{_PFX_PENDING}{pending_id}")

        if not raw:
            return HTMLResponse(
                "<h1>Session expired. Please retry.</h1>", status_code=400
            )
        pending = json.loads(raw)
        if pending["expires_at"] < time.time():
            await self._r.delete(f"{_PFX_PENDING}{pending_id}")
            return HTMLResponse(
                "<h1>Session expired. Please retry.</h1>", status_code=400
            )

        error = ""
        if request.method == "POST":
            form = await request.form()
            entered = str(form.get("api_key", ""))
            if INTERNAL_API_KEY and hmac.compare_digest(entered, INTERNAL_API_KEY):
                ap = AuthorizationParams(**pending["params"])
                client_id: str = pending["client_id"]
                await self._r.delete(f"{_PFX_PENDING}{pending_id}")

                code = secrets.token_urlsafe(32)
                code_obj = AuthorizationCode(
                    code=code,
                    scopes=ap.scopes or ["mcp"],
                    expires_at=time.time() + AUTH_CODE_TTL,
                    client_id=client_id,
                    code_challenge=ap.code_challenge,
                    redirect_uri=ap.redirect_uri,
                    redirect_uri_provided_explicitly=ap.redirect_uri_provided_explicitly,
                    resource=ap.resource,
                )
                await self._r.setex(
                    f"{_PFX_CODE}{code}", AUTH_CODE_TTL, _dumps(code_obj)
                )
                qs: dict[str, str] = {"code": code}
                if ap.state:
                    qs["state"] = ap.state
                return RedirectResponse(
                    f"{ap.redirect_uri}?{urlencode(qs)}", status_code=302
                )
            else:
                error = "Invalid API key. Please try again."

        client_id = pending["client_id"]
        return HTMLResponse(
            _consent_html(client_id=client_id, pending_id=pending_id, error=error)
        )

    # ── Authorization code exchange ───────────────────────────────────────────

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        raw = await self._r.get(f"{_PFX_CODE}{authorization_code}")
        if not raw:
            return None
        code = AuthorizationCode(**json.loads(raw))
        if code.client_id != client.client_id or code.expires_at <= time.time():
            return None
        return code

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        await self._r.delete(f"{_PFX_CODE}{authorization_code.code}")

        at = secrets.token_urlsafe(40)
        rt = secrets.token_urlsafe(40)
        exp = int(time.time()) + ACCESS_TOKEN_TTL

        at_obj = AccessToken(
            token=at,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=exp,
            resource=authorization_code.resource,
        )
        rt_obj = RefreshToken(
            token=rt,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=exp,
        )
        await self._r.setex(f"{_PFX_AT}{at}", ACCESS_TOKEN_TTL, _dumps(at_obj))
        await self._r.setex(f"{_PFX_RT}{rt}", ACCESS_TOKEN_TTL, _dumps(rt_obj))

        return OAuthToken(
            access_token=at,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_TTL,
            scope=" ".join(authorization_code.scopes),
            refresh_token=rt,
        )

    # ── Token validation & refresh ────────────────────────────────────────────

    async def load_access_token(self, token: str) -> AccessToken | None:
        raw = await self._r.get(f"{_PFX_AT}{token}")
        if not raw:
            return None
        at = AccessToken(**json.loads(raw))
        if at.expires_at is not None and at.expires_at <= time.time():
            await self._r.delete(f"{_PFX_AT}{token}")
            return None
        return at

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        raw = await self._r.get(f"{_PFX_RT}{refresh_token}")
        if not raw:
            return None
        rt = RefreshToken(**json.loads(raw))
        if rt.client_id != client.client_id:
            return None
        if rt.expires_at is not None and rt.expires_at <= time.time():
            await self._r.delete(f"{_PFX_RT}{refresh_token}")
            return None
        return rt

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        await self._r.delete(f"{_PFX_RT}{refresh_token.token}")

        at = secrets.token_urlsafe(40)
        rt = secrets.token_urlsafe(40)
        effective = scopes or refresh_token.scopes
        exp = int(time.time()) + ACCESS_TOKEN_TTL

        at_obj = AccessToken(
            token=at, client_id=client.client_id, scopes=effective, expires_at=exp
        )
        rt_obj = RefreshToken(
            token=rt, client_id=client.client_id, scopes=effective, expires_at=exp
        )
        await self._r.setex(f"{_PFX_AT}{at}", ACCESS_TOKEN_TTL, _dumps(at_obj))
        await self._r.setex(f"{_PFX_RT}{rt}", ACCESS_TOKEN_TTL, _dumps(rt_obj))

        return OAuthToken(
            access_token=at,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_TTL,
            scope=" ".join(effective),
            refresh_token=rt,
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            await self._r.delete(f"{_PFX_AT}{token.token}")
        else:
            await self._r.delete(f"{_PFX_RT}{token.token}")


# ── HTML consent page ─────────────────────────────────────────────────────────


def _consent_html(*, client_id: str, pending_id: str, error: str) -> str:
    error_html = f'<p class="error">{error}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OpenBrain — Authorize</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 400px; margin: 80px auto;
         padding: 0 1rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.25rem; }}
  .sub {{ color: #555; font-size: 0.9rem; margin-bottom: 1.5rem; }}
  label {{ display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.3rem; }}
  input[type=password] {{ width: 100%; box-sizing: border-box; padding: 0.5rem 0.75rem;
    border: 1px solid #ccc; border-radius: 6px; font-size: 1rem; }}
  button {{ margin-top: 1rem; width: 100%; padding: 0.6rem; background: #0070f3;
    color: #fff; border: none; border-radius: 6px; font-size: 1rem; cursor: pointer; }}
  button:hover {{ background: #0060df; }}
  .error {{ color: #c00; font-size: 0.9rem; margin-top: 0.5rem; }}
  .client {{ font-size: 0.8rem; color: #777; margin-top: 1.5rem; }}
</style>
</head>
<body>
<h1>OpenBrain</h1>
<p class="sub">A client is requesting access to your memory store.</p>
<form method="POST" action="/consent?pending_id={pending_id}">
  <label for="api_key">API Key</label>
  <input type="password" id="api_key" name="api_key"
         autocomplete="current-password"
         placeholder="Enter your INTERNAL_API_KEY" autofocus>
  {error_html}
  <button type="submit">Authorize</button>
</form>
<p class="client">Client: <code>{client_id}</code></p>
</body>
</html>"""


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    if not PUBLIC_BASE_URL_RAW.strip():
        raise SystemExit(
            "PUBLIC_BASE_URL is required for HTTP transport. "
            "Set it to the public URL of this server "
            "(e.g. https://poutily-hemispheroidal-pia.ngrok-free.dev)."
        )
    if not INTERNAL_API_KEY:
        raise SystemExit("INTERNAL_API_KEY is required for HTTP transport.")

    public_base_url = _normalize_public_base_url(PUBLIC_BASE_URL_RAW)
    port = _normalize_mcp_http_port(os.environ.get("MCP_HTTP_PORT", "7011"))

    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    auth = SimpleKeyOAuthProvider(base_url=public_base_url, redis=redis)

    # Register /consent as a custom route on the FastMCP instance
    @mcp.custom_route("/consent", methods=["GET", "POST"])
    async def consent(request: Request) -> HTMLResponse | RedirectResponse:
        return await auth.consent_handler(request)

    # OpenID Connect discovery — ChatGPT probes this; return OAuth AS metadata
    # in OIDC format so clients that prefer OIDC discovery don't get a 404.
    from starlette.responses import JSONResponse

    @mcp.custom_route("/.well-known/openid-configuration", methods=["GET"])
    async def oidc_discovery(request: Request) -> JSONResponse:
        base = public_base_url
        return JSONResponse(
            {
                "issuer": base,
                "authorization_endpoint": f"{base}/authorize",
                "token_endpoint": f"{base}/token",
                "registration_endpoint": f"{base}/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": [
                    "client_secret_post",
                    "client_secret_basic",
                ],
                "scopes_supported": ["mcp"],
            }
        )

    mcp.auth = auth

    # path="/" so that:
    #   - MCP endpoint is at the root (ChatGPT probes POST /)
    #   - /.well-known/oauth-protected-resource has no path suffix
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        path="/",
        log_level="info",
    )


if __name__ == "__main__":
    main()
