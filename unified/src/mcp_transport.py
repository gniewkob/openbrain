"""
MCP Streamable HTTP transport — Memory Platform V1.

Implements the canonical Tiered Hierarchy.
All tools now use the V1 API engine for consistent metadata handling.
"""

from __future__ import annotations

import os
import functools
from typing import Any, Literal, Optional
from urllib.parse import urlparse

import httpx
import structlog
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .capabilities_health import build_capabilities_health
from .capabilities_manifest import load_capabilities_manifest
from .capabilities_metadata import load_capabilities_metadata
from .http_error_adapter import backend_error_message, backend_request_failure_message
from .memory_paths import (
    memory_item_absolute_path,
    memory_item_path,
    memory_path,
)
from .request_builders import (
    build_find_list_payload,
    build_find_search_payload,
    build_list_filters,
    build_sync_check_payload,
    canonical_updated_by,
    normalize_updated_by,
)
from .response_normalizers import (
    normalize_find_hits_to_records,
    normalize_find_hits_to_scored_memories,
    to_legacy_memory_shape,
)
from .runtime_limits import load_runtime_limits

log = structlog.get_logger()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Config will be imported lazily to avoid circular imports
# BRAIN_URL is read from env at module level so importlib.reload picks up changes.
# _init_config() overrides these with the pydantic-settings config object when called.
BRAIN_URL: str = os.environ.get("BRAIN_URL", "http://127.0.0.1:80")
BACKEND_TIMEOUT: float = 30.0
HEALTH_PROBE_TIMEOUT: float = 5.0
INTERNAL_API_KEY: str = ""
ENABLE_HTTP_OBSIDIAN_TOOLS: bool = _env_bool("ENABLE_HTTP_OBSIDIAN_TOOLS", False)
MCP_SOURCE_SYSTEM: str = "other"
_public_base = ""
_ngrok_host = ""
STREAMABLE_HTTP_PATH = "/sse"
_CAPS = load_capabilities_manifest()
_CAP_META = load_capabilities_metadata()
CORE_TOOLS = _CAPS["core_tools"]
ADVANCED_TOOLS = _CAPS["advanced_tools"]
ADMIN_TOOLS = _CAPS["admin_tools"]
HTTP_OBSIDIAN_TOOLS = _CAPS["http_obsidian_tools"]
_LIMITS = load_runtime_limits()
MAX_SEARCH_TOP_K: int = _LIMITS["max_search_top_k"]
MAX_LIST_LIMIT: int = _LIMITS["max_list_limit"]
MAX_SYNC_LIMIT: int = _LIMITS["max_sync_limit"]
MAX_BULK_ITEMS: int = _LIMITS["max_bulk_items"]


def _http_obsidian_disabled_reason() -> str:
    return (
        "HTTP Obsidian tools are disabled by default. "
        "Set ENABLE_HTTP_OBSIDIAN_TOOLS=1 before starting transport."
    )


def _http_obsidian_tools_registered() -> bool:
    required = (
        "brain_obsidian_vaults",
        "brain_obsidian_read_note",
        "brain_obsidian_sync",
    )
    return all(callable(globals().get(name)) for name in required)


def _init_config():
    """Initialize module-level config from central config."""
    global \
        BRAIN_URL, \
        BACKEND_TIMEOUT, \
        HEALTH_PROBE_TIMEOUT, \
        INTERNAL_API_KEY, \
        STREAMABLE_HTTP_PATH, \
        MCP_SOURCE_SYSTEM, \
        _public_base, \
        _ngrok_host
    from .config import get_config

    config = get_config()
    BRAIN_URL = config.mcp.brain_url
    BACKEND_TIMEOUT = config.mcp.backend_timeout
    HEALTH_PROBE_TIMEOUT = config.mcp.health_probe_timeout
    INTERNAL_API_KEY = config.auth.internal_api_key
    STREAMABLE_HTTP_PATH = config.mcp.streamable_http_path
    MCP_SOURCE_SYSTEM = config.mcp.source_system
    _public_base = config.auth.public_base_url
    if _public_base:
        parsed = urlparse(
            _public_base if "://" in _public_base else f"https://{_public_base}"
        )
        _ngrok_host = parsed.hostname or ""
    else:
        _ngrok_host = ""


def _build_transport_security(ngrok_host: str) -> TransportSecuritySettings:
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"]
        + ([f"{ngrok_host}:*", ngrok_host] if ngrok_host else []),
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
        + ([f"https://{ngrok_host}"] if ngrok_host else []),
    )


_init_config()
_transport_security = _build_transport_security(_ngrok_host)

mcp = FastMCP(
    name="OpenBrain",
    streamable_http_path=STREAMABLE_HTTP_PATH,
    transport_security=_transport_security,
    instructions=(
        "OpenBrain is a unified memory platform with 3 domains: "
        "'corporate' (work), 'build' (projects), 'personal' (ideas).\n"
        "Always use brain_capabilities to check feature status. "
        "Use Tier 1 tools for daily interactions."
    ),
)

_SENSITIVE_LOG_FIELDS = {
    "content",
    "custom_fields",
    "match_key",
    "obsidian_ref",
    "tenant_id",
    "title",
}


def _client() -> "_SharedClient":
    return _SharedClient()


_http_client: httpx.AsyncClient | None = None
_http_client_config_key: tuple[str, float, str] | None = None


def _current_http_client_config_key() -> tuple[str, float, str]:
    return (BRAIN_URL, BACKEND_TIMEOUT, INTERNAL_API_KEY)


class _SharedClient:
    """Context-manager wrapper that reuses a single AsyncClient connection pool."""

    async def __aenter__(self) -> httpx.AsyncClient:
        global _http_client, _http_client_config_key
        current_key = _current_http_client_config_key()
        if _http_client is not None and _http_client_config_key != current_key:
            old_key = _http_client_config_key
            try:
                await _http_client.aclose()
            except Exception as exc:  # pragma: no cover - defensive logging path
                log.warning("mcp_client_close_failed", error=str(exc))
            log.info(
                "mcp_client_refreshed_due_to_config_drift",
                old_base_url=(old_key[0] if old_key else None),
                new_base_url=current_key[0],
            )
            _http_client = None
            _http_client_config_key = None

        if _http_client is None:
            headers: dict[str, str] = {}
            if INTERNAL_API_KEY:
                headers["X-Internal-Key"] = INTERNAL_API_KEY
            _http_client = httpx.AsyncClient(
                base_url=BRAIN_URL,
                timeout=BACKEND_TIMEOUT,
                headers=headers,
            )
            _http_client_config_key = current_key
        return _http_client

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def mcp_tool_guard(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            log.error("mcp_tool_error", tool=func.__name__, error=str(e))
            raise ValueError(f"Tool execution failed: {str(e)}") from e

    return wrapper


def _extract_record_from_write_response(payload: dict[str, Any]) -> dict[str, Any]:
    record = payload.get("record")
    if not isinstance(record, dict):
        raise ValueError(f"Write response missing record payload: {payload}")
    return to_legacy_memory_shape(record)


def _redact_logged_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        redacted = {}
        for key, value in payload.items():
            if key in _SENSITIVE_LOG_FIELDS:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_logged_payload(value)
        return redacted
    if isinstance(payload, list):
        return [_redact_logged_payload(item) for item in payload]
    return payload


async def _safe_req(method: str, path: str, **kwargs) -> dict[str, Any]:
    async with _client() as c:
        full_path = f"/api/v1/memory{path}" if not path.startswith("/api") else path
        if "json" in kwargs:
            # Redact record content to avoid PII/secrets leaking into log stores.
            _safe_payload = _redact_logged_payload(kwargs["json"])
            log.info(
                "mcp_v1_request", method=method, path=full_path, payload=_safe_payload
            )

        try:
            r = await c.request(method, full_path, **kwargs)
        except httpx.RequestError as exc:
            log.error(
                "mcp_v1_request_error",
                method=method,
                path=full_path,
                error=str(exc),
            )
            raise ValueError(backend_request_failure_message(exc)) from exc
        if r.is_error:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            log.error(
                "mcp_v1_error",
                method=method,
                path=full_path,
                code=r.status_code,
                detail=detail,
            )
            raise ValueError(backend_error_message(r.status_code, detail))
        return r.json() if r.status_code != 204 else {"status": "success"}


async def _get_backend_status() -> dict[str, Any]:
    """Probe backend readiness without conflating degradation with outage."""
    try:
        async with _client() as c:
            r = await c.request("GET", "/readyz", timeout=HEALTH_PROBE_TIMEOUT)
        data = r.json()
        if r.status_code in {200, 503} and isinstance(data, dict):
            return {
                "status": data.get(
                    "status",
                    "ok" if r.status_code == 200 else "degraded",
                ),
                "url": BRAIN_URL,
                "api": "reachable",
                "db": data.get("db", "unknown"),
                "vector_store": data.get("vector_store", "unknown"),
                "readyz_status_code": r.status_code,
                "probe": "readyz",
            }
        readyz_error = f"Unexpected /readyz response ({r.status_code})"
    except Exception as exc:
        readyz_error = str(exc)

    try:
        async with _client() as c:
            r = await c.request("GET", "/healthz", timeout=HEALTH_PROBE_TIMEOUT)
        if r.status_code == 200:
            return {
                "status": "degraded",
                "url": BRAIN_URL,
                "api": "reachable",
                "db": "unknown",
                "vector_store": "unknown",
                "probe": "healthz_fallback",
                "reason": f"/readyz probe failed: {readyz_error}",
            }
        healthz_error = f"Unexpected /healthz response ({r.status_code})"
    except Exception as exc:
        healthz_error = str(exc)

    try:
        async with _client() as c:
            r = await c.request("GET", "/api/v1/health", timeout=HEALTH_PROBE_TIMEOUT)
        if r.status_code == 200:
            return {
                "status": "degraded",
                "url": BRAIN_URL,
                "api": "reachable",
                "db": "unknown",
                "vector_store": "unknown",
                "probe": "api_health_fallback",
                "reason": (
                    f"/readyz probe failed: {readyz_error}; "
                    f"/healthz probe failed: {healthz_error}"
                ),
            }
        api_health_error = f"Unexpected /api/v1/health response ({r.status_code})"
    except Exception as exc:
        api_health_error = str(exc)

    return {
        "status": "unavailable",
        "url": BRAIN_URL,
        "api": "unreachable",
        "db": "unknown",
        "vector_store": "unknown",
        "probe": "api_health_fallback",
        "reason": (
            f"/readyz probe failed: {readyz_error}; "
            f"/healthz probe failed: {healthz_error}; "
            f"/api/v1/health probe failed: {api_health_error}"
        ),
    }


# ===========================================================================
# TIER 0: DIAGNOSTICS
# ===========================================================================


@mcp.tool()
@mcp_tool_guard
async def brain_capabilities() -> dict[str, Any]:
    """Check the operational status of the Memory Platform V1."""
    backend = await _get_backend_status()
    tier_2_tools = [*ADVANCED_TOOLS]
    obsidian_enabled = ENABLE_HTTP_OBSIDIAN_TOOLS and _http_obsidian_tools_registered()
    obsidian_tools = [*HTTP_OBSIDIAN_TOOLS] if obsidian_enabled else []
    obsidian_status = "enabled" if obsidian_enabled else "disabled"
    obsidian_reason = None if obsidian_enabled else _http_obsidian_disabled_reason()
    if obsidian_tools:
        tier_2_tools.extend(obsidian_tools)
    health = build_capabilities_health(backend, obsidian_status)
    return {
        "platform": "OpenBrain V1 (Industrial)",
        "api_version": _CAP_META["api_version"],
        "schema_changelog": _CAP_META["schema_changelog"],
        "backend": backend,
        "health": health,
        "obsidian": {
            "mode": "http",
            "status": obsidian_status,
            "tools": obsidian_tools,
            "reason": obsidian_reason,
        },
        "obsidian_http": {
            "status": obsidian_status,
            "tools": obsidian_tools,
            "reason": obsidian_reason,
        },
        "tier_1_core": {
            "status": "stable",
            "tools": CORE_TOOLS,
        },
        "tier_2_advanced": {
            "status": "active",
            "tools": tier_2_tools,
        },
        "tier_3_admin": {
            "status": "guarded",
            "tools": ADMIN_TOOLS,
        },
    }


# ===========================================================================
# TIER 1: CORE (PREFER THESE)
# ===========================================================================


@mcp.tool()
@mcp_tool_guard
async def brain_search(
    query: str,
    top_k: int = 5,
    domain: str | None = None,
    entity_type: str | None = None,
    owner: str | None = None,
    sensitivity: str | None = None,
) -> list[dict[str, Any]]:
    """Primary tool for semantic retrieval. Finds information by topic or phrase.

    Optionally filter by domain (corporate|build|personal), entity_type, owner,
    sensitivity.
    """
    if not 1 <= top_k <= MAX_SEARCH_TOP_K:
        raise ValueError(f"top_k must be 1–{MAX_SEARCH_TOP_K}, got {top_k}")
    filters = build_list_filters(
        domain=domain,
        entity_type=entity_type,
        sensitivity=sensitivity,
        owner=owner,
    )
    payload = build_find_search_payload(query=query, limit=top_k, filters=filters)
    return normalize_find_hits_to_scored_memories(
        await _safe_req("POST", memory_path("find"), json=payload)
    )


@mcp.tool()
@mcp_tool_guard
async def brain_get(memory_id: str) -> dict[str, Any]:
    """Retrieve a single memory by its exact ID.

    Returns canonical V1 MemoryRecord shape.
    """
    return await _safe_req("GET", memory_item_absolute_path(memory_id))


@mcp.tool()
@mcp_tool_guard
async def brain_store(
    content: str,
    domain: Literal["corporate", "build", "personal"] = "corporate",
    entity_type: str = "Note",
    title: Optional[str] = None,
    owner: str = "",
    tenant_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    custom_fields: Optional[dict[str, Any]] = None,
    match_key: Optional[str] = None,
    obsidian_ref: Optional[str] = None,
    sensitivity: Literal[
        "public", "internal", "confidential", "restricted"
    ] = "internal",
) -> dict[str, Any]:
    """
    Save a new memory to the platform.
    Ensures metadata (owner, tags, match_key) is preserved using the V1 write engine.
    """
    payload = {
        "record": {
            "content": content,
            "domain": domain,
            "entity_type": entity_type,
            "title": title,
            "owner": owner,
            "tenant_id": tenant_id,
            "tags": tags or [],
            "custom_fields": custom_fields or {},
            "match_key": match_key,
            "obsidian_ref": obsidian_ref,
            "sensitivity": sensitivity,
            "source": {"type": "agent", "system": MCP_SOURCE_SYSTEM},
        },
        "write_mode": "upsert",
    }
    result = await _safe_req("POST", memory_path("write"), json=payload)
    return _extract_record_from_write_response(result)


@mcp.tool()
@mcp_tool_guard
async def brain_update(
    memory_id: str,
    content: str,
    updated_by: str = "agent",
    title: Optional[str] = None,
    owner: Optional[str] = None,
    tenant_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    custom_fields: Optional[dict[str, Any]] = None,
    obsidian_ref: Optional[str] = None,
    sensitivity: Optional[str] = None,
) -> dict[str, Any]:
    """Update an existing memory.

    Corporate records are versioned automatically (append-only).
    The `updated_by` argument is accepted for backwards compatibility only.
    Audit actor identity is enforced server-side from authenticated subject.
    """
    _ = normalize_updated_by(updated_by)
    return await _safe_req(
        "PATCH",
        memory_item_path(memory_id),
        json={
            "content": content,
            "updated_by": canonical_updated_by(),
            "title": title,
            "owner": owner,
            "tenant_id": tenant_id,
            "tags": tags,
            "custom_fields": custom_fields,
            "obsidian_ref": obsidian_ref,
            "sensitivity": sensitivity,
        },
    )


# ===========================================================================
# TIER 2: ADVANCED
# ===========================================================================


@mcp.tool()
@mcp_tool_guard
async def brain_list(
    domain: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
    sensitivity: str | None = None,
    owner: str | None = None,
    tenant_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Browse memories with metadata filters.

    status options: active | superseded (default: active only)
    domain options: corporate | build | personal
    """
    if not 1 <= limit <= MAX_LIST_LIMIT:
        raise ValueError(f"limit must be 1–{MAX_LIST_LIMIT}, got {limit}")
    filters = build_list_filters(
        domain=domain,
        entity_type=entity_type,
        status=status,
        sensitivity=sensitivity,
        owner=owner,
        tenant_id=tenant_id,
    )
    payload = build_find_list_payload(limit=limit, filters=filters)
    hits = await _safe_req("POST", memory_path("find"), json=payload)
    return normalize_find_hits_to_records(hits)


@mcp.tool()
@mcp_tool_guard
async def brain_get_context(query: str, domain: Optional[str] = None) -> dict[str, Any]:
    """Synthesize a grounding pack for the current conversation topic."""
    payload = {"query": query, "domain": domain, "max_items": 10}
    return await _safe_req("POST", memory_path("get_context"), json=payload)


@mcp.tool()
@mcp_tool_guard
async def brain_delete(memory_id: str) -> dict[str, Any]:
    """Delete a memory. Forbidden for corporate domain."""
    await _safe_req("DELETE", f"/{memory_id}")
    return {"deleted": True, "id": memory_id}


@mcp.tool()
@mcp_tool_guard
async def brain_export(ids: list[str]) -> list[dict[str, Any]]:
    """Export raw memory records for external use."""
    return await _safe_req("POST", memory_path("export"), json={"ids": ids})


@mcp.tool()
@mcp_tool_guard
async def brain_sync_check(
    memory_id: str | None = None,
    match_key: str | None = None,
    obsidian_ref: str | None = None,
    file_hash: str | None = None,
) -> dict[str, Any]:
    """Check whether a memory exists or matches a provided content hash."""
    payload = build_sync_check_payload(
        memory_id=memory_id,
        match_key=match_key,
        obsidian_ref=obsidian_ref,
        file_hash=file_hash,
    )
    return await _safe_req("POST", memory_path("sync_check"), json=payload)


if ENABLE_HTTP_OBSIDIAN_TOOLS:

    @mcp.tool()
    @mcp_tool_guard
    async def brain_obsidian_vaults() -> Any:
        """List local Obsidian vaults available to the backend."""
        return await _safe_req("GET", "/api/v1/obsidian/vaults")

    @mcp.tool()
    @mcp_tool_guard
    async def brain_obsidian_read_note(
        path: str, vault: str = "Documents"
    ) -> dict[str, Any]:
        """Read a note from a local Obsidian vault with parsed frontmatter and tags."""
        return await _safe_req(
            "POST", "/api/v1/obsidian/read-note", json={"vault": vault, "path": path}
        )

    @mcp.tool()
    @mcp_tool_guard
    async def brain_obsidian_sync(
        vault: str = "Documents",
        paths: list[str] | None = None,
        folder: str | None = None,
        limit: int = 50,
        domain: Literal["corporate", "build", "personal"] = "build",
        entity_type: str = "Architecture",
        owner: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        One-way sync from an Obsidian vault into OpenBrain using deterministic
        match keys. Use paths for explicit notes or folder for a bounded folder sync.
        """
        if not 1 <= limit <= MAX_SYNC_LIMIT:
            raise ValueError(f"limit must be 1–{MAX_SYNC_LIMIT}, got {limit}")
        payload = {
            "vault": vault,
            "paths": paths or [],
            "folder": folder,
            "limit": limit,
            "domain": domain,
            "entity_type": entity_type,
            "owner": owner,
            "tags": tags or [],
        }
        return await _safe_req("POST", "/api/v1/obsidian/sync", json=payload)

# ===========================================================================
# TIER 3: ADMIN
# ===========================================================================


@mcp.tool()
@mcp_tool_guard
async def brain_store_bulk(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Bulk store memories. Use for archiving or synchronization.

    Args:
        items: List of memory records (max 100 per batch)
    """
    if len(items) > MAX_BULK_ITEMS:
        raise ValueError(
            f"Batch size exceeds maximum of {MAX_BULK_ITEMS} items. "
            "Split into multiple calls."
        )
    if not items:
        raise ValueError("Batch cannot be empty.")
    payload = {"records": items, "write_mode": "upsert"}
    return await _safe_req("POST", memory_path("write_many"), json=payload)


@mcp.tool()
@mcp_tool_guard
async def brain_upsert_bulk(items: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Idempotent bulk synchronization using match_key.

    Args:
        items: List of memory records (max 100 per batch)
    """
    if len(items) > MAX_BULK_ITEMS:
        raise ValueError(
            f"Batch size exceeds maximum of {MAX_BULK_ITEMS} items. "
            "Split into multiple calls."
        )
    if not items:
        raise ValueError("Batch cannot be empty.")
    return await _safe_req("POST", memory_path("bulk_upsert"), json=items)


@mcp.tool()
@mcp_tool_guard
async def brain_maintain(dry_run: bool = True) -> dict[str, Any]:
    """Run system maintenance tasks (deduplication, normalization)."""
    return await _safe_req("POST", memory_path("maintain"), json={"dry_run": dry_run})
