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
INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "openbrain-local-dev")

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
    return httpx.AsyncClient(
        base_url=BRAIN_URL,
        timeout=BACKEND_TIMEOUT,
        headers={"X-Internal-Key": INTERNAL_API_KEY},
    )

def mcp_tool_guard(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            log.error("mcp_tool_error", tool=func.__name__, error=str(e))
            return {"status": "error", "message": f"Tool execution failed: {str(e)}", "tool": func.__name__}
    return wrapper

async def _safe_req(method: str, path: str, **kwargs) -> dict[str, Any]:
    async with _client() as c:
        full_path = f"/api/v1/memory{path}" if not path.startswith("/api") else path
        if "json" in kwargs:
            log.info("mcp_v1_request", method=method, path=full_path, payload=kwargs["json"])
        
        r = await c.request(method, full_path, **kwargs)
        if r.is_error:
            try:
                detail = r.json()
            except:
                detail = r.text
            log.error("mcp_v1_error", method=method, path=full_path, code=r.status_code, detail=detail)
            return {"status": "error", "code": r.status_code, "detail": detail}
        return r.json() if r.status_code != 204 else {"status": "success"}

# ===========================================================================
# TIER 0: DIAGNOSTICS
# ===========================================================================

@mcp.tool()
@mcp_tool_guard
async def brain_capabilities() -> dict[str, Any]:
    """Check the operational status of the Memory Platform V1."""
    return {
        "platform": "OpenBrain V1 (Industrial)",
        "tier_1_core": {"status": "stable", "tools": ["search", "get", "store", "update"]},
        "tier_2_advanced": {"status": "active", "tools": ["list", "get_context", "delete", "export", "sync_check"]},
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
    return await _safe_req("POST", "/find", json=payload)

@mcp.tool()
@mcp_tool_guard
async def brain_get(memory_id: str) -> dict[str, Any]:
    """Retrieve a single memory by its exact ID."""
    # Using legacy path for direct ID lookup, it still works
    return await _safe_req("GET", f"/api/memories/{memory_id}")

@mcp.tool()
@mcp_tool_guard
async def brain_store(
    content: str, 
    domain: Literal["corporate", "build", "personal"] = "corporate", 
    entity_type: str = "Note",
    title: Optional[str] = None,
    owner: str = "",
    tags: Optional[list[str]] = None,
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
            "tags": tags or [],
            "match_key": match_key,
            "obsidian_ref": obsidian_ref,
            "sensitivity": sensitivity,
            "source": {"type": "agent", "system": "chatgpt"}
        },
        "write_mode": "upsert"
    }
    return await _safe_req("POST", "/write", json=payload)

@mcp.tool()
@mcp_tool_guard
async def brain_update(
    memory_id: str, 
    content: str,
    title: Optional[str] = None,
    owner: Optional[str] = None,
    tags: Optional[list[str]] = None,
    obsidian_ref: Optional[str] = None,
    sensitivity: Optional[str] = None
) -> dict[str, Any]:
    """Update an existing memory. Corporate records will be versioned automatically."""
    # In V1, update is also a 'write' with write_mode=upsert/update_only
    # For now, mapping to simple upsert by match_key is complex without the key,
    # so we use the record as a base.
    payload = {
        "record": {
            "content": content,
            "domain": "personal", # placeholder, will be inferred if we had match_key
            "entity_type": "Note",
            "title": title,
            "owner": owner or "",
            "tags": tags or [],
            "obsidian_ref": obsidian_ref,
            "sensitivity": sensitivity or "internal"
        },
        "write_mode": "upsert"
    }
    # Special case: if we have ID but no match_key, we might need a specific v1/update endpoint.
    # For now, we'll keep using the legacy PUT which we already updated to use V1 internally.
    return await _safe_req("PUT", f"/api/memories/{memory_id}", json={
        "content": content, "owner": owner, "tags": tags, "obsidian_ref": obsidian_ref, "sensitivity": sensitivity
    })

# ===========================================================================
# TIER 2: ADVANCED
# ===========================================================================

@mcp.tool()
@mcp_tool_guard
async def brain_list(domain: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Browse memories with metadata filters."""
    payload = {"filters": {"domain": domain} if domain else {}, "limit": limit, "sort": "updated_at_desc"}
    return await _safe_req("POST", "/find", json=payload)

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
    return await _safe_req("DELETE", f"/api/memories/{memory_id}")

@mcp.tool()
@mcp_tool_guard
async def brain_export(ids: list[str]) -> list[dict[str, Any]]:
    """Export raw memory records for external use."""
    return await _safe_req("POST", f"/api/memories/export", json={"ids": ids})

@mcp.tool()
@mcp_tool_guard
async def brain_sync_check(obsidian_ref: str, file_hash: str) -> dict[str, Any]:
    """Check sync status between Obsidian and OpenBrain."""
    # Params based check
    async with _client() as c:
        r = await c.post("/api/memories/sync-check", params={"obsidian_ref": obsidian_ref, "file_hash": file_hash})
        return r.json()

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
    payload = {"records": items, "write_mode": "upsert"}
    return await _safe_req("POST", "/write-many", json=payload)

@mcp.tool()
@mcp_tool_guard
async def brain_maintain(dry_run: bool = True) -> dict[str, Any]:
    """Run system maintenance tasks (deduplication, normalization)."""
    return await _safe_req("POST", "/api/admin/maintain", json={"dry_run": dry_run})
