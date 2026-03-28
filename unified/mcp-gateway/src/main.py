"""
OpenBrain Unified MCP Gateway — exposes brain_* tools to Claude Code via stdio.

Lightweight proxy to the unified memory service at BRAIN_URL (default: http://127.0.0.1:7010).
Runs as stdio transport for Claude Code MCP integration.

Tools:
  brain_capabilities    — runtime capability summary
  brain_store           — save a new memory (corporate/build/personal domain)
  brain_get             — retrieve memory by ID
  brain_list            — list with filters
  brain_search          — semantic similarity search
  brain_update          — update memory (corporate: append-only versioning, build/personal: in-place)
  brain_delete          — delete memory (build/personal only, corporate forbidden)
  brain_get_context     — synthesize grounding context pack
  brain_store_bulk      — batch store records
  brain_upsert_bulk     — idempotent batch upsert
  brain_maintain        — dedup + owner normalization
  brain_export          — controlled transfer export
  brain_sync_check      — memory sync/existence check by ID, match_key, or obsidian_ref
  brain_obsidian_vaults — list local Obsidian vaults
  brain_obsidian_read_note — read a local Obsidian note
  brain_obsidian_sync   — one-way sync from Obsidian into OpenBrain
"""
from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel

from .obsidian_cli import ObsidianCliAdapter, ObsidianCliError, note_to_write_payload

BRAIN_URL: str = os.environ.get("BRAIN_URL", "http://localhost:7010")
BACKEND_TIMEOUT: float = float(os.environ.get("BACKEND_TIMEOUT_S", "30"))
INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "").strip()

mcp = FastMCP(
    name="OpenBrain",
    instructions=(
        "OpenBrain is your unified knowledge base — one brain for all domains.\n"
        "Use domain='corporate' for professional work decisions, policies, and meeting notes.\n"
        "Use domain='build' for technical code, side projects, and architecture.\n"
        "Use domain='personal' for personal notes, goals, ideas.\n\n"
        "Corporate memories are append-only (versioned, audited, cannot be deleted).\n"
        "Build/personal memories are mutable and deletable.\n\n"
        "Always tag memories with relevant domain + area tags.\n"
        "Use brain_search to find relevant context across all domains."
    ),
)


class BrainMemory(BaseModel):
    id: str
    tenant_id: str | None = None
    domain: str
    entity_type: str
    content: str
    owner: str = ""
    status: str
    version: int
    sensitivity: str
    superseded_by: str | None = None
    tags: list[str] = []
    relations: dict[str, Any] = {}
    obsidian_ref: str | None = None
    custom_fields: dict[str, Any] = {}
    content_hash: str = ""
    match_key: str | None = None
    previous_id: str | None = None
    root_id: str | None = None
    valid_from: str | None = None
    created_at: str
    updated_at: str
    created_by: str
    updated_by: str | None = None


def _client() -> httpx.AsyncClient:
    headers = {}
    if INTERNAL_API_KEY:
        headers["X-Internal-Key"] = INTERNAL_API_KEY
    return httpx.AsyncClient(
        base_url=BRAIN_URL,
        timeout=BACKEND_TIMEOUT,
        headers=headers,
    )


def _raise(r: httpx.Response) -> None:
    if r.is_error:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise ValueError(f"Backend {r.status_code}: {detail}")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def brain_capabilities() -> dict:
    """Check the operational status of the Memory Platform V1."""
    return {
        "platform": "OpenBrain V1 (Gateway)",
        "tier_1_core": {"status": "stable", "tools": ["search", "get", "store", "update"]},
        "tier_2_advanced": {
            "status": "active",
            "tools": ["list", "get_context", "delete", "export", "sync_check", "obsidian_vaults", "obsidian_read_note", "obsidian_sync"],
        },
        "tier_3_admin": {"status": "guarded", "tools": ["store_bulk", "upsert_bulk", "maintain"]},
    }


@mcp.tool()
async def brain_store(
    content: str,
    domain: Literal["corporate", "build", "personal"] = "corporate",
    entity_type: str = "Decision",
    title: str | None = None,
    sensitivity: str = "internal",
    owner: str = "",
    tenant_id: str | None = None,
    created_by: str = "agent",
    tags: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
    obsidian_ref: str | None = None,
    match_key: str | None = None,
) -> BrainMemory:
    """
    Save a new memory to OpenBrain.

    domain:
      - corporate: professional work. Append-only, audited.
      - build: technical/side projects. Mutable.
      - personal: personal notes, goals. Mutable.

    entity_type examples:
      Corporate: Decision | Policy | Risk | MeetingNote | Vendor | Service | Architecture
      Build: Project | CodeSnippet | Bug | Feature | Idea
      Personal: Note | Book | Music | Recipe | Travel | Goal

    tags — add at least one domain tag + area tag:
      ["engineering", "auth"], ["project-x", "frontend"], ["personal", "reading"]

    match_key — optional idempotency key for bulk sync (prevents duplicates).
    obsidian_ref — path to source note in Obsidian vault.
    """
    async with _client() as c:
        r = await c.post("/api/memories", json={
            "content": content,
            "domain": domain,
            "entity_type": entity_type,
            "title": title,
            "sensitivity": sensitivity,
            "owner": owner,
            "tenant_id": tenant_id,
            "created_by": created_by,
            "tags": tags or [],
            "custom_fields": custom_fields or {},
            "obsidian_ref": obsidian_ref,
            "match_key": match_key,
        })
        _raise(r)
        return BrainMemory(**r.json())


@mcp.tool()
async def brain_get(memory_id: str) -> BrainMemory:
    """Retrieve a specific memory by its ID."""
    async with _client() as c:
        r = await c.get(f"/api/memories/{memory_id}")
        if r.status_code == 404:
            raise ValueError(f"Memory not found: {memory_id}")
        _raise(r)
        return BrainMemory(**r.json())


@mcp.tool()
async def brain_list(
    domain: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
    sensitivity: str | None = None,
    owner: str | None = None,
    tenant_id: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """
    List memories with optional filters.
    status options: active | draft | deprecated (superseded excluded by default).
    domain options: corporate | build | personal.
    """
    params: dict[str, Any] = {"limit": limit}
    if domain:
        params["domain"] = domain
    if entity_type:
        params["entity_type"] = entity_type
    if status:
        params["status"] = status
    if sensitivity:
        params["sensitivity"] = sensitivity
    if owner:
        params["owner"] = owner
    if tenant_id:
        params["tenant_id"] = tenant_id

    async with _client() as c:
        r = await c.get("/api/memories", params=params)
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_get_context(query: str, domain: str | None = None) -> dict:
    """Synthesize a grounding pack for the current conversation topic."""
    async with _client() as c:
        r = await c.post("/api/v1/memory/get-context", json={"query": query, "domain": domain, "max_items": 10})
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_search(
    query: str,
    top_k: int = 5,
    domain: str | None = None,
    entity_type: str | None = None,
    sensitivity: str | None = None,
) -> list[dict]:
    """
    Semantic search across the unified knowledge base.
    Returns top-k memories most relevant to the query.
    Optionally filter by domain (corporate|build|personal), entity_type, sensitivity.
    """
    filters: dict[str, Any] = {}
    if domain:
        filters["domain"] = domain
    if entity_type:
        filters["entity_type"] = entity_type
    if sensitivity:
        filters["sensitivity"] = sensitivity

    async with _client() as c:
        r = await c.post("/api/memories/search", json={
            "query": query,
            "top_k": top_k,
            "filters": filters,
        })
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_update(
    memory_id: str,
    content: str,
    title: str | None = None,
    updated_by: str = "agent",
    sensitivity: str | None = None,
    owner: str | None = None,
    tenant_id: str | None = None,
    tags: list[str] | None = None,
    custom_fields: dict[str, Any] | None = None,
    obsidian_ref: str | None = None,
) -> BrainMemory:
    """
    Update a memory.
    - Corporate: creates new version (append-only). Old version marked as superseded.
    - Build/Personal: updates in place.
    """
    payload: dict[str, Any] = {"content": content, "updated_by": updated_by}
    if title is not None:
        payload["title"] = title
    if sensitivity:
        payload["sensitivity"] = sensitivity
    if owner is not None:
        payload["owner"] = owner
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    if tags is not None:
        payload["tags"] = tags
    if custom_fields is not None:
        payload["custom_fields"] = custom_fields
    if obsidian_ref is not None:
        payload["obsidian_ref"] = obsidian_ref

    async with _client() as c:
        r = await c.put(f"/api/memories/{memory_id}", json=payload)
        if r.status_code == 404:
            raise ValueError(f"Memory not found: {memory_id}")
        _raise(r)
        return BrainMemory(**r.json())


@mcp.tool()
async def brain_delete(memory_id: str) -> dict:
    """
    Delete a memory. Only allowed for build/personal domains.
    Corporate memories cannot be deleted (returns 403).
    """
    async with _client() as c:
        r = await c.delete(f"/api/memories/{memory_id}")
        if r.status_code == 404:
            raise ValueError(f"Memory not found: {memory_id}")
        if r.status_code == 403:
            raise ValueError("Cannot delete corporate memories. Use deprecation instead.")
        _raise(r)
        return {"deleted": True, "id": memory_id}


@mcp.tool()
async def brain_maintain(
    dry_run: bool = True,
    dedup_threshold: float = 0.05,
    normalize_owners: dict[str, str] | None = None,
    fix_superseded_links: bool = True,
) -> dict:
    """
    Bulk maintenance: dedup, owner normalization, superseded_by repair.
    Always run with dry_run=True first to preview changes.
    """
    async with _client() as c:
        r = await c.post("/api/admin/maintain", json={
            "dry_run": dry_run,
            "dedup_threshold": dedup_threshold,
            "normalize_owners": normalize_owners or {},
            "retype_rules": [],
            "fix_superseded_links": fix_superseded_links,
        })
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_export(ids: list[str]) -> list[dict]:
    """
    Export memories for review or transfer.
    Restricted-sensitivity content is redacted automatically.
    """
    async with _client() as c:
        r = await c.post("/api/memories/export", json={"ids": ids, "format": "jsonl"})
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_sync_check(
    memory_id: str | None = None,
    match_key: str | None = None,
    obsidian_ref: str | None = None,
    file_hash: str | None = None,
) -> dict:
    """
    Check whether a memory exists or is up to date.
    Provide exactly one of memory_id, match_key, or obsidian_ref.
    If file_hash is omitted, returns existence status only.
    """
    payload: dict[str, Any] = {
        "memory_id": memory_id,
        "match_key": match_key,
        "obsidian_ref": obsidian_ref,
        "file_hash": file_hash,
    }
    async with _client() as c:
        r = await c.post("/api/memories/sync-check", json=payload)
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_obsidian_vaults() -> list[str]:
    """List local Obsidian vaults available to the backend."""
    adapter = ObsidianCliAdapter()
    try:
        return await adapter.list_vaults()
    except ObsidianCliError as e:
        raise ValueError(str(e))


@mcp.tool()
async def brain_obsidian_read_note(path: str, vault: str = "Documents") -> dict:
    """Read a note from a local Obsidian vault with parsed frontmatter and tags."""
    adapter = ObsidianCliAdapter()
    try:
        note = await adapter.read_note(vault, path)
    except ObsidianCliError as e:
        raise ValueError(str(e))
    return {
        "vault": note.vault,
        "path": note.path,
        "title": note.title,
        "content": note.content,
        "frontmatter": note.frontmatter,
        "tags": note.tags,
        "file_hash": note.file_hash,
    }


@mcp.tool()
async def brain_obsidian_sync(
    vault: str = "Documents",
    paths: list[str] | None = None,
    folder: str | None = None,
    limit: int = 50,
    domain: Literal["corporate", "build", "personal"] = "build",
    entity_type: str = "Architecture",
    owner: str = "",
    tags: list[str] | None = None,
) -> dict:
    """
    One-way sync from an Obsidian vault into OpenBrain using deterministic match keys.
    Use paths for explicit notes or folder for a bounded folder sync.
    """
    adapter = ObsidianCliAdapter()
    try:
        resolved_paths = (paths or [])[:limit] if paths else await adapter.list_files(vault, folder=folder, limit=limit)
        notes = [await adapter.read_note(vault, path) for path in resolved_paths]
    except ObsidianCliError as e:
        raise ValueError(str(e))

    payload = {
        "records": [
            note_to_write_payload(
                note,
                default_domain=domain,
                default_entity_type=entity_type,
                default_owner=owner,
                default_tags=tags or [],
            )
            for note in notes
        ],
        "write_mode": "upsert",
    }
    async with _client() as c:
        r = await c.post("/api/v1/memory/write-many", json=payload)
        _raise(r)
        result = r.json()
        return {
            "vault": vault,
            "resolved_paths": resolved_paths,
            "scanned": len(resolved_paths),
            "summary": result.get("summary", {}),
            "results": result.get("results", []),
        }


@mcp.tool()
async def brain_store_bulk(items: list[dict[str, Any]]) -> dict:
    """Bulk store memories. Use for archiving or synchronization."""
    async with _client() as c:
        r = await c.post("/api/v1/memory/write-many", json={"records": items, "write_mode": "upsert"})
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_upsert_bulk(items: list[dict[str, Any]]) -> dict:
    """Idempotent bulk synchronization using match_key."""
    async with _client() as c:
        r = await c.post("/api/memories/bulk-upsert", json=items)
        _raise(r)
        return r.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
