"""
OIDC/Auth0 Validation for OpenBrain Unified v2.0.

When PUBLIC_MODE=true or PUBLIC_BASE_URL is set, all protected endpoints require
a valid Auth0 JWT or the trusted internal key. Otherwise all requests pass
through for local use.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

logger = logging.getLogger("openbrain.auth")

PUBLIC_MODE = os.environ.get("PUBLIC_MODE", "").lower() == "true"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip()
PUBLIC_EXPOSURE = PUBLIC_MODE or bool(PUBLIC_BASE_URL)
LOCAL_DEV_INTERNAL_API_KEY = "openbrain-local-dev"
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "").strip()

OIDC_ISSUER_URL = os.environ.get("OIDC_ISSUER_URL", "").strip().rstrip("/")
OIDC_AUDIENCE = os.environ.get("OIDC_AUDIENCE", "https://openbrain-mcp").strip()
OIDC_DISCOVERY_CACHE_S = int(os.environ.get("OIDC_DISCOVERY_CACHE_S", "600"))
POLICY_REGISTRY_JSON = os.environ.get("OPENBRAIN_POLICY_REGISTRY_JSON", "").strip()
POLICY_REGISTRY_PATH = os.environ.get("OPENBRAIN_POLICY_REGISTRY_PATH", "").strip()

_bearer_scheme = HTTPBearer(auto_error=False)
_local_auth_warning_emitted = False


@dataclass
class OIDCMetadata:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    introspection_endpoint: Optional[str] = None
    registration_endpoint: Optional[str] = None


class OIDCVerifier:
    def __init__(
        self, issuer_url: str, audience: str = "", discovery_cache_s: int = 600
    ):
        self.issuer_url = issuer_url.rstrip("/")
        self.audience = audience
        self.discovery_cache_s = max(60, discovery_cache_s)
        self._metadata: OIDCMetadata | None = None
        self._metadata_fetched_at = 0.0
        self._jwk_client: PyJWKClient | None = None
        self._refresh_lock: asyncio.Lock | None = None

    def _get_refresh_lock(self) -> asyncio.Lock:
        if self._refresh_lock is None:
            self._refresh_lock = asyncio.Lock()
        return self._refresh_lock

    async def metadata(self) -> OIDCMetadata:
        now = time.time()
        if (
            self._metadata
            and (now - self._metadata_fetched_at) < self.discovery_cache_s
        ):
            return self._metadata

        # Lock prevents concurrent requests from all issuing discovery calls.
        async with self._get_refresh_lock():
            # Re-check inside lock — another coroutine may have refreshed first.
            now = time.time()
            if (
                self._metadata
                and (now - self._metadata_fetched_at) < self.discovery_cache_s
            ):
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
                raise RuntimeError(
                    f"OIDC discovery failed for issuer: {self.issuer_url}"
                )

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
        """
        Verify and decode a JWT access token.

        Args:
            token: JWT access token to verify

        Returns:
            Decoded token claims

        Raises:
            ValueError: If token is invalid or verification fails
        """
        await self.metadata()

        if len(token.split(".")) != 3:
            raise ValueError("Invalid access token: not a JWT")

        try:
            signing_key = await asyncio.to_thread(
                self._jwk_client.get_signing_key_from_jwt,  # type: ignore[union-attr]
                token,
            )
            # audience=None silently disables PyJWT audience validation — always
            # pass a non-empty string so misconfiguration raises, not silently passes.
            if not self.audience:
                raise ValueError(
                    "OIDC_AUDIENCE is not configured; refusing to accept tokens "
                    "without audience validation."
                )
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self._metadata.issuer,  # type: ignore[union-attr]
                options={
                    "require": ["exp", "iat", "sub"],
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                },
            )
            sub = str(claims.get("sub", "")).strip()
            if not sub:
                raise ValueError("Token missing required 'sub' claim")
            return claims
        except ValueError:
            raise
        except Exception as e:
            # Log full details server-side; return a generic message to avoid
            # leaking expiry times, issuer, audience hints to the caller.
            logger.error("JWT verification failed: %s", e)
            raise ValueError("Invalid access token") from e


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


# asyncio.Lock for async write path — never blocks the event loop.
# Reads use direct dict reference (atomic under CPython GIL, no lock needed).
_policy_registry_write_lock = asyncio.Lock()


def _merge_policy_registry(
    base: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, Any]:
    merged = {
        "tenants": dict(base.get("tenants", {})),
        "subjects": dict(base.get("subjects", {})),
    }
    for key in ("tenants", "subjects"):
        for scope_id, scope_value in overlay.get(key, {}).items():
            merged[key][scope_id] = scope_value
    return merged


def _load_policy_registry_from_json() -> dict[str, Any]:
    if not POLICY_REGISTRY_JSON:
        return {"tenants": {}, "subjects": {}}
    try:
        parsed = json.loads(POLICY_REGISTRY_JSON)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OPENBRAIN_POLICY_REGISTRY_JSON is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("OPENBRAIN_POLICY_REGISTRY_JSON must be a JSON object")
    return parsed


def _load_policy_registry_from_file() -> dict[str, Any]:
    if not POLICY_REGISTRY_PATH:
        return {"tenants": {}, "subjects": {}}
    path = Path(POLICY_REGISTRY_PATH)
    if not path.exists():
        return {"tenants": {}, "subjects": {}}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "OPENBRAIN_POLICY_REGISTRY_PATH does not contain valid JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("OPENBRAIN_POLICY_REGISTRY_PATH must contain a JSON object")
    return parsed


def _load_policy_registry() -> dict[str, Any]:
    env_registry = _load_policy_registry_from_json()
    file_registry = _load_policy_registry_from_file()
    return _merge_policy_registry(env_registry, file_registry)


POLICY_REGISTRY: dict[str, Any] = _load_policy_registry()


def _current_registry() -> dict[str, Any]:
    """Return the current policy registry snapshot.

    Dict reference replacement is atomic under CPython GIL — no lock required for reads.
    """
    return POLICY_REGISTRY


def get_policy_registry() -> dict[str, Any]:
    """Get current policy registry configuration.

    Returns:
        Dictionary with tenants and subjects policy configuration
    """
    ref = _current_registry()
    return {
        "tenants": dict(ref.get("tenants", {})),
        "subjects": dict(ref.get("subjects", {})),
    }


async def set_policy_registry(registry: dict[str, Any]) -> dict[str, Any]:
    """
    Set the policy registry atomically and persist to disk.

    Args:
        registry: Policy registry with tenants and subjects configuration

    Returns:
        Updated policy registry
    """
    global POLICY_REGISTRY
    normalized = {
        "tenants": dict(registry.get("tenants", {})),
        "subjects": dict(registry.get("subjects", {})),
    }
    async with _policy_registry_write_lock:
        # Atomic reference replacement — no clear()+update() race window.
        POLICY_REGISTRY = normalized
    if POLICY_REGISTRY_PATH:
        # Disk write is blocking I/O — run in thread pool to avoid
        # blocking the event loop.
        def _write() -> None:
            import stat

            path = Path(POLICY_REGISTRY_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8"
            )
            # Restrict to owner-only (rw-------) — contains access control rules
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)

        await asyncio.to_thread(_write)
    return get_policy_registry()


def validate_security_configuration() -> None:
    """
    Validate security configuration for public exposure.

    Raises:
        RuntimeError: If required security settings are missing in public mode
    """
    if not PUBLIC_EXPOSURE:
        return
    # Require at least one auth mechanism: OIDC or a non-default INTERNAL_API_KEY.
    # OIDC is optional when callers authenticate exclusively via X-Internal-Key
    # (e.g. ChatGPT MCP, local MCP gateway). Missing both leaves the server open.
    has_internal_key = (
        bool(INTERNAL_API_KEY) and INTERNAL_API_KEY != LOCAL_DEV_INTERNAL_API_KEY
    )
    if not OIDC_ISSUER_URL and not has_internal_key:
        raise RuntimeError(
            "PUBLIC_MODE=true or PUBLIC_BASE_URL set requires either OIDC_ISSUER_URL "
            "or a non-default INTERNAL_API_KEY. Refusing to start with no auth."
        )
    if not INTERNAL_API_KEY:
        raise RuntimeError(
            "PUBLIC_MODE=true or PUBLIC_BASE_URL set requires INTERNAL_API_KEY "
            "for trusted internal callers."
        )
    if INTERNAL_API_KEY == LOCAL_DEV_INTERNAL_API_KEY:
        raise RuntimeError(
            "PUBLIC_MODE=true or PUBLIC_BASE_URL set forbids the dev default "
            "INTERNAL_API_KEY. Configure a unique secret."
        )


validate_security_configuration()


def get_subject(claims: dict[str, Any]) -> str:
    """Extract subject identifier from JWT claims.

    Args:
        claims: JWT payload containing user claims

    Returns:
        Subject identifier (sub claim) or empty string
    """
    return str(claims.get("sub", "")).strip()


def get_tenant_id(claims: dict[str, Any]) -> str:
    """Extract tenant ID from JWT claims.

    Checks multiple claim keys in order of preference:
    tenant_id, tenant, tid, org_id, organization_id

    Args:
        claims: JWT payload containing tenant claims

    Returns:
        Tenant identifier or empty string if not found
    """
    for key in (
        "tenant_id",
        "tenant",
        "tid",
        "org_id",
        "organization_id",
        "https://openbrain/tenant_id",
    ):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _claim_values(claims: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        value = claims.get(key)
        if isinstance(value, str):
            values.extend(
                part.strip() for part in value.replace(",", " ").split() if part.strip()
            )
        elif isinstance(value, list):
            values.extend(str(part).strip() for part in value if str(part).strip())
    return values


def get_domain_scope(claims: dict[str, Any], action: str) -> set[str]:
    """Extract domain scope for given action from JWT claims.

    Args:
        claims: JWT payload with domain scope claims
        action: Action type (read, write, admin)

    Returns:
        Set of allowed domains for the action
    """
    action = action.lower()
    direct_keys = {
        "read": (
            "read_domains",
            "allowed_domains",
            "https://openbrain/read_domains",
            "https://openbrain/allowed_domains",
        ),
        "write": (
            "write_domains",
            "allowed_domains",
            "https://openbrain/write_domains",
            "https://openbrain/allowed_domains",
        ),
        "admin": (
            "admin_domains",
            "allowed_domains",
            "https://openbrain/admin_domains",
            "https://openbrain/allowed_domains",
        ),
    }
    values = _claim_values(claims, *direct_keys.get(action, ()))
    normalized = {value.lower() for value in values if value.strip()}
    return {
        value for value in normalized if value in {"corporate", "build", "personal"}
    }


def get_registry_domain_scope(subject: str, tenant_id: str, action: str) -> set[str]:
    action = action.lower()
    allowed_domains = {"corporate", "build", "personal"}

    def _extract(entry: Any) -> set[str]:
        if not isinstance(entry, dict):
            return set()
        values = entry.get(f"{action}_domains") or entry.get("allowed_domains") or []
        if isinstance(values, str):
            values = [
                part.strip()
                for part in values.replace(",", " ").split()
                if part.strip()
            ]
        if not isinstance(values, list):
            return set()
        return {
            str(value).lower()
            for value in values
            if str(value).lower() in allowed_domains
        }

    # Read a consistent snapshot under lock to avoid race with set_policy_registry.
    registry = _current_registry()
    scopes: set[str] = set()
    tenant_entry = registry.get("tenants", {}).get(tenant_id, {}) if tenant_id else {}
    subject_entry = registry.get("subjects", {}).get(subject, {}) if subject else {}
    scopes |= _extract(tenant_entry)
    scopes |= _extract(subject_entry)
    return scopes


def is_privileged_user(claims: dict[str, Any]) -> bool:
    """Check if user has privileged/admin access based on claims.

    Args:
        claims: JWT payload with role claims

    Returns:
        True if user has admin/privileged role
    """
    subject = get_subject(claims)
    # "local-dev" is returned only when public exposure is disabled — always trusted.
    # "internal" is privileged only when it arrived via X-Internal-Key, not via
    # a JWT whose sub field happens to contain "internal" (C2 fix).
    if subject == "local-dev":
        return True
    if subject == "internal" and claims.get("_auth_via_internal_key"):
        return True

    role_values: list[str] = []
    for key in (
        "roles",
        "role",
        "permissions",
        "permission",
        "scope",
        "scp",
        "https://openbrain/roles",
    ):
        value = claims.get(key)
        if isinstance(value, str):
            role_values.extend(
                part.strip() for part in value.replace(",", " ").split() if part.strip()
            )
        elif isinstance(value, list):
            role_values.extend(str(part).strip() for part in value if str(part).strip())

    normalized = {value.lower() for value in role_values}
    return any(
        value in normalized for value in {"admin", "openbrain:admin", "maintain:admin"}
    )


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, Any]:
    """FastAPI dependency. Returns JWT claims or local-dev stub.

    Auth is skipped when:
    - public exposure is disabled (all local)
    - Request carries X-Internal-Key matching INTERNAL_API_KEY (MCP gateway)
    When PUBLIC_MODE is true or PUBLIC_BASE_URL is set and no internal key:
    requires Auth0 JWT.
    """
    if not PUBLIC_EXPOSURE:
        global _local_auth_warning_emitted
        if not _local_auth_warning_emitted:
            logger.warning(
                "Authentication is disabled because PUBLIC_MODE and "
                "PUBLIC_BASE_URL are unset; local-only access is permitted "
                "for this process."
            )
            _local_auth_warning_emitted = True
        return {"sub": "local-dev"}

    # Allow MCP gateway (and curl) to bypass OIDC with internal key.
    # hmac.compare_digest prevents timing-attack guessing of INTERNAL_API_KEY.
    # _auth_via_internal_key is injected so is_privileged_user can distinguish
    # this path from a JWT whose sub happens to be "internal".
    internal_key = request.headers.get("X-Internal-Key", "")
    if (
        internal_key
        and INTERNAL_API_KEY
        and hmac.compare_digest(internal_key, INTERNAL_API_KEY)
    ):
        return {"sub": "internal", "_auth_via_internal_key": True}

    if not _oidc:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    try:
        return await _oidc.verify_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
