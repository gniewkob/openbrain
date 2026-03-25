"""
OIDC/Auth0 Validation for OpenBrain Unified v2.0.

When PUBLIC_MODE=true, all mutating endpoints require a valid Auth0 JWT.
When PUBLIC_MODE is unset/false (default), all requests pass through (local use).
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt as jose_jwt
from jwt import PyJWKClient

logger = logging.getLogger("openbrain.auth")

PUBLIC_MODE = os.environ.get("PUBLIC_MODE", "").lower() == "true"
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "openbrain-local-dev")

OIDC_ISSUER_URL = os.environ.get(
    "OIDC_ISSUER_URL", ""
).strip().rstrip("/")
OIDC_AUDIENCE = os.environ.get("OIDC_AUDIENCE", "https://openbrain-mcp").strip()
OIDC_DISCOVERY_CACHE_S = int(os.environ.get("OIDC_DISCOVERY_CACHE_S", "600"))

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class OIDCMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    introspection_endpoint: Optional[str] = None
    registration_endpoint: Optional[str] = None


class OIDCVerifier:
    def __init__(self, issuer_url: str, audience: str = "", discovery_cache_s: int = 600):
        self.issuer_url = issuer_url.rstrip("/")
        self.audience = audience
        self.discovery_cache_s = max(60, discovery_cache_s)
        self._metadata: OIDCMetadata | None = None
        self._metadata_fetched_at = 0.0
        self._jwk_client: PyJWKClient | None = None

    async def metadata(self) -> OIDCMetadata:
        now = time.time()
        if self._metadata and (now - self._metadata_fetched_at) < self.discovery_cache_s:
            return self._metadata

        openid_cfg = f"{self.issuer_url}/.well-known/openid-configuration"
        payload = None
        async with httpx.AsyncClient(timeout=10) as c:
            try:
                r = await c.get(openid_cfg)
                if r.status_code == 200:
                    payload = r.json()
            except httpx.HTTPError as e:
                logger.error("OIDC discovery failed: %s", e)

        if payload is None:
            raise RuntimeError(f"OIDC discovery failed for issuer: {self.issuer_url}")

        self._metadata = OIDCMetadata(
            issuer=payload["issuer"],
            authorization_endpoint=payload["authorization_endpoint"],
            token_endpoint=payload["token_endpoint"],
            jwks_uri=payload["jwks_uri"],
            introspection_endpoint=payload.get("introspection_endpoint"),
            registration_endpoint=payload.get("registration_endpoint"),
        )
        self._metadata_fetched_at = now
        self._jwk_client = PyJWKClient(self._metadata.jwks_uri)
        return self._metadata

    async def verify_token(self, token: str) -> dict[str, Any]:
        await self.metadata()

        if len(token.split(".")) != 3:
            raise ValueError("Invalid access token: not a JWT")

        try:
            signing_key = await asyncio.to_thread(
                self._jwk_client.get_signing_key_from_jwt,  # type: ignore[union-attr]
                token,
            )
            claims = jose_jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience or None,
                issuer=self._metadata.issuer,  # type: ignore[union-attr]
            )
            return claims
        except Exception as e:
            logger.error("JWT verification failed: %s", e)
            raise ValueError(f"Invalid access token: {e}") from e


# Singleton — created only if issuer URL is set.
_oidc: OIDCVerifier | None = (
    OIDCVerifier(
        issuer_url=OIDC_ISSUER_URL,
        audience=OIDC_AUDIENCE,
        discovery_cache_s=OIDC_DISCOVERY_CACHE_S,
    )
    if OIDC_ISSUER_URL
    else None
)


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """FastAPI dependency. Returns JWT claims or local-dev stub.

    Auth is skipped when:
    - PUBLIC_MODE is false (all local)
    - Request carries X-Internal-Key matching INTERNAL_API_KEY (MCP gateway)
    When PUBLIC_MODE is true and no internal key: requires Auth0 JWT.
    """
    if not PUBLIC_MODE:
        return {"sub": "local-dev"}

    # Allow MCP gateway (and curl) to bypass OIDC with internal key
    internal_key = request.headers.get("X-Internal-Key")
    if internal_key and internal_key == INTERNAL_API_KEY:
        return {"sub": "internal"}

    if not _oidc:
        return {"sub": "local-dev"}

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    try:
        return await _oidc.verify_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
