"""
OpenBrain Unified MCP Gateway — exposes brain_* tools to Claude Code via stdio.

Lightweight proxy to the unified memory service at BRAIN_URL (default: http://127.0.0.1:7010).
Runs as stdio transport for Claude Code MCP integration.

Tools:
  brain_store           — save a new memory (corporate/build/personal domain)
  brain_get             — retrieve memory by ID
  brain_list            — list with filters
  brain_search          — semantic similarity search
  brain_update          — update memory (corporate: append-only versioning, build/personal: in-place)
  brain_delete          — delete memory (build/personal only, corporate forbidden)
  brain_maintain        — dedup + owner normalization
  brain_export          — controlled transfer export
  brain_sync_check      — Obsidian sync hash check
"""
from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel

BRAIN_URL: str = os.environ.get("BRAIN_URL", "http://localhost:7010")
BACKEND_TIMEOUT: float = float(os.environ.get("BACKEND_TIMEOUT_S", "30"))
INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "openbrain-local-dev")

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
    content_hash: str = ""
    match_key: str | None = None
    valid_from: str | None = None
    created_at: str
    updated_at: str
    created_by: str


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BRAIN_URL,
        timeout=BACKEND_TIMEOUT,
        headers={"X-Internal-Key": INTERNAL_API_KEY},
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
async def brain_store(
    content: str,
    domain: Literal["corporate", "build", "personal"] = "corporate",
    entity_type: str = "Decision",
    sensitivity: str = "internal",
    owner: str = "",
    created_by: str = "agent",
    tags: list[str] | None = None,
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
        r = await c.post("/memories", json={
            "content": content,
            "domain": domain,
            "entity_type": entity_type,
            "sensitivity": sensitivity,
            "owner": owner,
            "created_by": created_by,
            "tags": tags or [],
            "obsidian_ref": obsidian_ref,
            "match_key": match_key,
        })
        _raise(r)
        return BrainMemory(**r.json())


@mcp.tool()
async def brain_get(memory_id: str) -> BrainMemory:
    """Retrieve a specific memory by its ID."""
    async with _client() as c:
        r = await c.get(f"/memories/{memory_id}")
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

    async with _client() as c:
        r = await c.get("/memories", params=params)
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
        r = await c.post("/memories/search", json={
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
    updated_by: str = "agent",
    sensitivity: str | None = None,
    owner: str | None = None,
    tags: list[str] | None = None,
) -> BrainMemory:
    """
    Update a memory.
    - Corporate: creates new version (append-only). Old version marked as superseded.
    - Build/Personal: updates in place.
    """
    payload: dict[str, Any] = {"content": content, "updated_by": updated_by}
    if sensitivity:
        payload["sensitivity"] = sensitivity
    if owner is not None:
        payload["owner"] = owner
    if tags is not None:
        payload["tags"] = tags

    async with _client() as c:
        r = await c.put(f"/memories/{memory_id}", json=payload)
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
        r = await c.delete(f"/memories/{memory_id}")
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
        r = await c.post("/admin/maintain", json={
            "dry_run": dry_run,
            "dedup_threshold": dedup_threshold,
            "normalize_owners": normalize_owners or {},
            "retype_rules": [],
            "fix_superseded_links": fix_superseded_links,
        })
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_export(memory_ids: list[str]) -> list[dict]:
    """
    Export memories for review or transfer.
    Restricted-sensitivity content is redacted automatically.
    """
    async with _client() as c:
        r = await c.post("/memories/export", json={"ids": memory_ids, "format": "jsonl"})
        _raise(r)
        return r.json()


@mcp.tool()
async def brain_sync_check(obsidian_ref: str, file_hash: str) -> dict:
    """
    Check if an Obsidian note needs updating in OpenBrain.
    Returns: {status: "synced"|"outdated"|"missing", message: "..."}
    """
    async with _client() as c:
        r = await c.post("/memories/sync-check", params={
            "obsidian_ref": obsidian_ref,
            "file_hash": file_hash,
        })
        _raise(r)
        return r.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
