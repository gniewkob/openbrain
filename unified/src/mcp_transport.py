"""
MCP Streamable HTTP transport — Memory Platform V1.

Implements the canonical Tiered Hierarchy.
All tools now use the V1 API engine for consistent metadata handling.
"""
from __future__ import annotations

import os
import functools
import json
from typing import Any, Literal, Optional

import httpx
import structlog
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

log = structlog.get_logger()

BRAIN_URL: str = "http://localhost:80"
BACKEND_TIMEOUT: float = 30.0
INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "").strip()
ENABLE_HTTP_OBSIDIAN_TOOLS: bool = os.environ.get("ENABLE_HTTP_OBSIDIAN_TOOLS", "").lower() in {"1", "true", "yes"}
# Source system tag stored with every brain_store call.
# Override via MCP_SOURCE_SYSTEM env var when running from a non-ChatGPT host.
MCP_SOURCE_SYSTEM: str = os.environ.get("MCP_SOURCE_SYSTEM", "other")

_public_base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
_ngrok_host = _public_base.replace("https://", "").replace("http://", "") if _public_base else ""

_transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"] + ([f"{_ngrok_host}:*", _ngrok_host] if _ngrok_host else []),
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"] + ([f"https://{_ngrok_host}"] if _ngrok_host else []),
)

mcp = FastMCP(
    name="OpenBrain",
    streamable_http_path="/sse",
    transport_security=_transport_security,
    instructions=(
        "OpenBrain is a unified memory platform with 3 domains: 'corporate' (work), 'build' (projects), 'personal' (ideas).\n"
        "Always use brain_capabilities to check feature status. Use Tier 1 tools for daily interactions."
    )
)

def _client() -> httpx.AsyncClient:
    headers = {}
    if INTERNAL_API_KEY:
        headers["X-Internal-Key"] = INTERNAL_API_KEY
    return httpx.AsyncClient(
        base_url=BRAIN_URL,
        timeout=BACKEND_TIMEOUT,
        headers=headers,
    )

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
    return _to_legacy_memory_shape(record)


def _to_legacy_memory_shape(record: dict[str, Any]) -> dict[str, Any]:
    legacy_keys = (
        "id",
        "tenant_id",
        "domain",
        "entity_type",
        "content",
        "owner",
        "status",
        "version",
        "sensitivity",
        "superseded_by",
        "tags",
        "relations",
        "obsidian_ref",
        "custom_fields",
        "content_hash",
        "match_key",
        "previous_id",
        "root_id",
        "valid_from",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    )
    return {key: record.get(key) for key in legacy_keys}


def _normalize_search_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for hit in hits:
        if isinstance(hit, dict) and "record" in hit and "score" in hit:
            normalized.append({"memory": _to_legacy_memory_shape(hit["record"]), "score": hit["score"]})
        else:
            normalized.append(hit)
    return normalized


async def _safe_req(method: str, path: str, **kwargs) -> dict[str, Any]:
    async with _client() as c:
        full_path = f"/api/v1/memory{path}" if not path.startswith("/api") else path
        if "json" in kwargs:
            log.info("mcp_v1_request", method=method, path=full_path, payload=kwargs["json"])
        
        r = await c.request(method, full_path, **kwargs)
        if r.is_error:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            log.error("mcp_v1_error", method=method, path=full_path, code=r.status_code, detail=detail)
            raise ValueError(f"Backend {r.status_code}: {json.dumps(detail, ensure_ascii=False) if isinstance(detail, (dict, list)) else detail}")
        return r.json() if r.status_code != 204 else {"status": "success"}

# ===========================================================================
# TIER 0: DIAGNOSTICS
# ===========================================================================

@mcp.tool()
@mcp_tool_guard
async def brain_capabilities() -> dict[str, Any]:
    """Check the operational status of the Memory Platform V1."""
    tier_2_tools = ["list", "get_context", "delete", "export", "sync_check"]
    if ENABLE_HTTP_OBSIDIAN_TOOLS:
        tier_2_tools.extend(["obsidian_vaults", "obsidian_read_note", "obsidian_sync"])
    return {
        "platform": "OpenBrain V1 (Industrial)",
        "tier_1_core": {"status": "stable", "tools": ["search", "get", "store", "update"]},
        "tier_2_advanced": {
            "status": "active",
            "tools": tier_2_tools,
        },
        "tier_3_admin": {"status": "guarded", "tools": ["store_bulk", "upsert_bulk", "maintain"]}
    }

# ===========================================================================
# TIER 1: CORE (PREFER THESE)
# ===========================================================================

@mcp.tool()
@mcp_tool_guard
async def brain_search(query: str, top_k: int = 5, domain: str | None = None) -> list[dict[str, Any]]:
    """Primary tool for semantic retrieval. Finds information by topic or phrase."""
    payload = {"query": query, "limit": top_k, "filters": {"domain": domain} if domain else {}}
    return _normalize_search_hits(await _safe_req("POST", "/find", json=payload))

@mcp.tool()
@mcp_tool_guard
async def brain_get(memory_id: str) -> dict[str, Any]:
    """Retrieve a single memory by its exact ID. Returns canonical V1 MemoryRecord shape."""
    return await _safe_req("GET", f"/api/v1/memory/{memory_id}")

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
    sensitivity: Literal["public", "internal", "confidential", "restricted"] = "internal"
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
            "source": {"type": "agent", "system": MCP_SOURCE_SYSTEM}
        },
        "write_mode": "upsert"
    }
    result = await _safe_req("POST", "/write", json=payload)
    return _extract_record_from_write_response(result)

@mcp.tool()
@mcp_tool_guard
async def brain_update(
    memory_id: str,
    content: str,
    title: Optional[str] = None,
    owner: Optional[str] = None,
    tenant_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    custom_fields: Optional[dict[str, Any]] = None,
    obsidian_ref: Optional[str] = None,
    sensitivity: Optional[str] = None,
) -> dict[str, Any]:
    """Update an existing memory. Corporate records are versioned automatically (append-only)."""
    return await _safe_req("PUT", f"/api/memories/{memory_id}", json={
        "content": content,
        "title": title,
        "owner": owner,
        "tenant_id": tenant_id,
        "tags": tags,
        "custom_fields": custom_fields,
        "obsidian_ref": obsidian_ref,
        "sensitivity": sensitivity,
    })

# ===========================================================================
# TIER 2: ADVANCED
# ===========================================================================

@mcp.tool()
@mcp_tool_guard
async def brain_list(domain: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Browse memories with metadata filters."""
    params: dict[str, Any] = {"limit": limit}
    if domain:
        params["domain"] = domain
    return await _safe_req("GET", "/api/memories", params=params)

@mcp.tool()
@mcp_tool_guard
async def brain_get_context(query: str, domain: Optional[str] = None) -> dict[str, Any]:
    """Synthesize a grounding pack for the current conversation topic."""
    payload = {"query": query, "domain": domain, "max_items": 10}
    return await _safe_req("POST", "/get-context", json=payload)

@mcp.tool()
@mcp_tool_guard
async def brain_delete(memory_id: str) -> dict[str, Any]:
    """Delete a memory. Forbidden for corporate domain."""
    await _safe_req("DELETE", f"/api/memories/{memory_id}")
    return {"deleted": True, "id": memory_id}

@mcp.tool()
@mcp_tool_guard
async def brain_export(ids: list[str]) -> list[dict[str, Any]]:
    """Export raw memory records for external use."""
    return await _safe_req("POST", f"/api/memories/export", json={"ids": ids})

@mcp.tool()
@mcp_tool_guard
async def brain_sync_check(
    memory_id: str | None = None,
    match_key: str | None = None,
    obsidian_ref: str | None = None,
    file_hash: str | None = None,
) -> dict[str, Any]:
    """Check whether a memory exists or matches a provided content hash."""
    return await _safe_req("POST", "/api/memories/sync-check", json={
        "memory_id": memory_id,
        "match_key": match_key,
        "obsidian_ref": obsidian_ref,
        "file_hash": file_hash,
    })


if ENABLE_HTTP_OBSIDIAN_TOOLS:
    @mcp.tool()
    @mcp_tool_guard
    async def brain_obsidian_vaults() -> Any:
        """List local Obsidian vaults available to the backend."""
        return await _safe_req("GET", "/api/v1/obsidian/vaults")


    @mcp.tool()
    @mcp_tool_guard
    async def brain_obsidian_read_note(path: str, vault: str = "Documents") -> dict[str, Any]:
        """Read a note from a local Obsidian vault with parsed frontmatter and tags."""
        return await _safe_req("POST", "/api/v1/obsidian/read-note", json={"vault": vault, "path": path})


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
        One-way sync from an Obsidian vault into OpenBrain using deterministic match keys.
        Use paths for explicit notes or folder for a bounded folder sync.
        """
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
    """Bulk store memories. Use for archiving or synchronization."""
    payload = {"records": items, "write_mode": "upsert"}
    return await _safe_req("POST", "/write-many", json=payload)

@mcp.tool()
@mcp_tool_guard
async def brain_upsert_bulk(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Idempotent bulk synchronization using match_key."""
    return await _safe_req("POST", "/api/memories/bulk-upsert", json=items)

@mcp.tool()
@mcp_tool_guard
async def brain_maintain(dry_run: bool = True) -> dict[str, Any]:
    """Run system maintenance tasks (deduplication, normalization)."""
    return await _safe_req("POST", "/api/admin/maintain", json={"dry_run": dry_run})
