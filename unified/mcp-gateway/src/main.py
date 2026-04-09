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
  brain_obsidian_write_note — write a local Obsidian note
  brain_obsidian_export — export memories to local Obsidian notes
  brain_obsidian_collection — build an Obsidian collection note from memories
  brain_obsidian_bidirectional_sync — sync OpenBrain and Obsidian in both directions
  brain_obsidian_sync_status — inspect bidirectional sync status
  brain_obsidian_update_note — update an existing local Obsidian note
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel

from .capabilities_health import build_capabilities_health
from .capabilities_manifest import load_capabilities_manifest
from .capabilities_metadata import load_capabilities_metadata
from .http_error_adapter import backend_error_message, backend_request_failure_message
from .memory_paths import memory_absolute_path, memory_item_absolute_path
from .obsidian_cli import ObsidianCliAdapter, ObsidianCliError, note_to_write_payload
from .request_builders import (
    build_find_list_payload,
    build_find_search_payload,
    build_list_filters,
    build_sync_check_payload,
    canonical_updated_by,
    normalize_optional_text,
    normalize_updated_by,
    validate_store_inputs,
)
from .response_normalizers import (
    normalize_find_hits_to_records,
    normalize_find_hits_to_scored_memories,
)
from .runtime_limits import load_runtime_limits

_gateway_logger = logging.getLogger("mcp_gateway")

BRAIN_URL: str = os.environ.get("BRAIN_URL", "http://localhost:7010")
BACKEND_TIMEOUT_RAW: str = os.environ.get("BACKEND_TIMEOUT_S", "30")
BACKEND_TIMEOUT: float
HEALTH_PROBE_TIMEOUT_RAW: str = os.environ.get("MCP_HEALTH_PROBE_TIMEOUT_S", "5.0")
HEALTH_PROBE_TIMEOUT: float
INTERNAL_API_KEY: str = os.environ.get("INTERNAL_API_KEY", "").strip()
OBSIDIAN_LOCAL_TOOLS_ENV = "ENABLE_LOCAL_OBSIDIAN_TOOLS"
MCP_SOURCE_SYSTEM_RAW: str = os.environ.get(
    "MCP_SOURCE_SYSTEM",
    os.environ.get("SOURCE_SYSTEM", "other"),
)
MCP_SOURCE_SYSTEM: str

_MIN_KEY_LEN = 32


def _normalize_brain_url(value: str | None) -> str:
    normalized = (value or "").strip()
    if any(ch.isspace() for ch in normalized):
        raise ValueError("BRAIN_URL must not include whitespace")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("BRAIN_URL must be a valid http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("BRAIN_URL must not include credentials")
    if parsed.path not in {"", "/"}:
        raise ValueError("BRAIN_URL must not include path")
    if parsed.query or parsed.fragment:
        raise ValueError("BRAIN_URL must not include query params or fragment")
    return normalized.rstrip("/")


def _normalize_backend_timeout(value: str | None) -> float:
    try:
        normalized = float((value or "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("BACKEND_TIMEOUT_S must be a valid float") from exc
    if not math.isfinite(normalized):
        raise ValueError("BACKEND_TIMEOUT_S must be finite")
    if normalized <= 0:
        raise ValueError("BACKEND_TIMEOUT_S must be > 0")
    if normalized > 120:
        raise ValueError("BACKEND_TIMEOUT_S must be <= 120")
    return normalized


def _normalize_health_probe_timeout(value: str | None, backend_timeout: float) -> float:
    try:
        normalized = float((value or "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("MCP_HEALTH_PROBE_TIMEOUT_S must be a valid float") from exc
    if not math.isfinite(normalized):
        raise ValueError("MCP_HEALTH_PROBE_TIMEOUT_S must be finite")
    if normalized <= 0:
        raise ValueError("MCP_HEALTH_PROBE_TIMEOUT_S must be > 0")
    if normalized > 30:
        raise ValueError("MCP_HEALTH_PROBE_TIMEOUT_S must be <= 30")
    if normalized > backend_timeout:
        raise ValueError("MCP_HEALTH_PROBE_TIMEOUT_S must be <= BACKEND_TIMEOUT_S")
    return normalized


def _normalize_source_system(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", normalized):
        raise ValueError("MCP_SOURCE_SYSTEM must match [a-z0-9][a-z0-9_-]{0,31}")
    return normalized


BRAIN_URL = _normalize_brain_url(BRAIN_URL)
BACKEND_TIMEOUT = _normalize_backend_timeout(BACKEND_TIMEOUT_RAW)
HEALTH_PROBE_TIMEOUT = _normalize_health_probe_timeout(
    HEALTH_PROBE_TIMEOUT_RAW,
    BACKEND_TIMEOUT,
)
MCP_SOURCE_SYSTEM = _normalize_source_system(MCP_SOURCE_SYSTEM_RAW)

if INTERNAL_API_KEY and len(INTERNAL_API_KEY) < _MIN_KEY_LEN:
    _gateway_logger.warning(
        "INTERNAL_API_KEY is only %d chars (minimum %d recommended). "
        "Use a longer key in production.",
        len(INTERNAL_API_KEY),
        _MIN_KEY_LEN,
    )
elif not INTERNAL_API_KEY:
    _gateway_logger.warning(
        "INTERNAL_API_KEY is not set. Requests to backend will fail in public mode."
    )

# Parameter validation bounds (PERF-007)
_LIMITS = load_runtime_limits()
MAX_SEARCH_TOP_K: int = _LIMITS["max_search_top_k"]
MAX_LIST_LIMIT: int = _LIMITS["max_list_limit"]
MAX_SYNC_LIMIT: int = _LIMITS["max_sync_limit"]

_CAPS = load_capabilities_manifest()
_CAP_META = load_capabilities_metadata()
CORE_TOOLS = _CAPS["core_tools"]
ADVANCED_TOOLS = _CAPS["advanced_tools"]
ADMIN_TOOLS = _CAPS["admin_tools"]
OBSIDIAN_LOCAL_TOOLS = _CAPS["local_obsidian_tools"]

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
    title: str | None = None
    summary: str | None = None
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
    source: dict[str, Any] | None = None
    governance: dict[str, Any] | None = None


_http_client: httpx.AsyncClient | None = None


class _SharedClient:
    """Context-manager wrapper that lazily creates and reuses a single AsyncClient.

    All 'async with _client() as c:' call sites work unchanged while the underlying
    client (and its connection pool) is shared across requests.
    """

    async def __aenter__(self) -> httpx.AsyncClient:
        global _http_client
        if _http_client is None:
            headers: dict[str, str] = {}
            if INTERNAL_API_KEY:
                headers["X-Internal-Key"] = INTERNAL_API_KEY
            _http_client = httpx.AsyncClient(
                base_url=BRAIN_URL,
                timeout=BACKEND_TIMEOUT,
                headers=headers,
            )
        return _http_client

    async def __aexit__(self, *_: object) -> None:
        pass  # Keep client alive for connection-pool reuse


def _client() -> _SharedClient:
    return _SharedClient()


def _raise(r: httpx.Response) -> None:
    if r.is_error:
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise ValueError(backend_error_message(r.status_code, detail))


async def _request_or_raise(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    allow_statuses: set[int] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    try:
        # Prefer verb-specific methods first to preserve existing test/mocking
        # patterns, then fall back to generic request().
        method_fn = getattr(client, method.lower(), None)
        if callable(method_fn):
            response = await method_fn(path, **kwargs)
        else:
            request_fn = getattr(client, "request", None)
            if not callable(request_fn):
                raise ValueError(f"Client does not support method {method}")
            response = await request_fn(method, path, **kwargs)
    except httpx.RequestError as exc:
        raise ValueError(backend_request_failure_message(exc)) from exc

    if response.is_error and (
        allow_statuses is None or response.status_code not in allow_statuses
    ):
        _raise(response)
    return response


def _obsidian_local_tools_enabled() -> bool:
    return os.environ.get(OBSIDIAN_LOCAL_TOOLS_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _obsidian_local_tools_disabled_reason() -> str:
    return (
        "Local Obsidian tools are disabled by default. "
        f"Set {OBSIDIAN_LOCAL_TOOLS_ENV}=1 only on a trusted local stdio gateway."
    )


def _require_obsidian_local_tools_enabled() -> None:
    if _obsidian_local_tools_enabled():
        return
    raise ValueError(_obsidian_local_tools_disabled_reason())


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


async def _get_backend_status() -> dict:
    """Probe backend readiness without conflating degradation with outage."""
    try:
        async with httpx.AsyncClient(timeout=HEALTH_PROBE_TIMEOUT) as client:
            r = await client.get(f"{BRAIN_URL}/readyz")
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
        async with httpx.AsyncClient(timeout=HEALTH_PROBE_TIMEOUT) as client:
            r = await client.get(f"{BRAIN_URL}/healthz")
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


@mcp.tool()
async def brain_capabilities() -> dict:
    """Check the operational status of the Memory Platform V1."""
    obsidian_enabled = _obsidian_local_tools_enabled()
    backend = await _get_backend_status()
    tier_2_tools = [*ADVANCED_TOOLS]
    obsidian_tools = [*OBSIDIAN_LOCAL_TOOLS] if obsidian_enabled else []
    obsidian_status = "enabled" if obsidian_enabled else "disabled"
    obsidian_reason = None if obsidian_enabled else _obsidian_local_tools_disabled_reason()
    if obsidian_tools:
        tier_2_tools.extend(obsidian_tools)
    health = build_capabilities_health(backend, obsidian_status)

    return {
        "platform": "OpenBrain V1 (Gateway)",
        "api_version": _CAP_META["api_version"],
        "schema_changelog": _CAP_META["schema_changelog"],
        "backend": backend,
        "health": health,
        "obsidian": {
            "mode": "local",
            "status": obsidian_status,
            "tools": obsidian_tools,
            "reason": obsidian_reason,
        },
        "obsidian_local": {
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


@mcp.tool()
async def brain_store(
    content: str,
    domain: Literal["corporate", "build", "personal"] = "corporate",
    entity_type: str = "Decision",
    title: str | None = None,
    sensitivity: str = "internal",
    owner: str = "",
    tenant_id: str | None = None,
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
    owner_normalized = normalize_optional_text(owner) or ""
    match_key_normalized = normalize_optional_text(match_key)
    validate_store_inputs(
        domain=domain,
        owner=owner_normalized,
        match_key=match_key_normalized,
    )

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("write"),
            json={
                "record": {
                    "content": content,
                    "domain": domain,
                    "entity_type": entity_type,
                    "title": title,
                    "sensitivity": sensitivity,
                    "owner": owner_normalized,
                    "tenant_id": tenant_id,
                    "tags": tags or [],
                    "custom_fields": custom_fields or {},
                    "obsidian_ref": obsidian_ref,
                    "match_key": match_key_normalized,
                    "source": {"type": "agent", "system": MCP_SOURCE_SYSTEM},
                },
                "write_mode": "upsert",
            },
        )
        return BrainMemory(**r.json()["record"])


@mcp.tool()
async def brain_get(memory_id: str) -> BrainMemory:
    """Retrieve a specific memory by its ID."""
    async with _client() as c:
        r = await _request_or_raise(
            c, "GET", memory_item_absolute_path(memory_id), allow_statuses={404}
        )
        if r.status_code == 404:
            raise ValueError(f"Memory not found: {memory_id}")
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
    Browse memories with metadata filters.

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

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("find"),
            json=payload,
        )
        return normalize_find_hits_to_records(r.json())


@mcp.tool()
async def brain_get_context(query: str, domain: str | None = None) -> dict:
    """Synthesize a grounding pack for the current conversation topic."""
    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("get_context"),
            json={"query": query, "domain": domain, "max_items": 10},
        )
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
    if not 1 <= top_k <= MAX_SEARCH_TOP_K:
        raise ValueError(f"top_k must be 1–{MAX_SEARCH_TOP_K}, got {top_k}")
    filters = build_list_filters(
        domain=domain,
        entity_type=entity_type,
        sensitivity=sensitivity,
    )
    payload = build_find_search_payload(query=query, limit=top_k, filters=filters)

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("find"),
            json=payload,
        )
        return normalize_find_hits_to_scored_memories(r.json())


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
    Update a memory by ID.
    - Corporate: creates new version (append-only). Old version marked as superseded.
    - Build/Personal: updates in place.
    - `updated_by` is compatibility-only and not authoritative for audit identity.
    """
    _ = normalize_updated_by(updated_by)
    # Build patch payload — only include fields explicitly provided
    payload: dict[str, Any] = {
        "content": content,
        "updated_by": canonical_updated_by(),
    }
    if title is not None:
        payload["title"] = title
    if sensitivity is not None:
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
        r = await _request_or_raise(
            c,
            "PATCH",
            memory_item_absolute_path(memory_id),
            allow_statuses={404},
            json=payload,
        )
        if r.status_code == 404:
            raise ValueError(f"Memory not found: {memory_id}")
        return BrainMemory(**r.json())


@mcp.tool()
async def brain_delete(memory_id: str) -> dict:
    """
    Delete a memory. Only allowed for build/personal domains.
    Corporate memories cannot be deleted (returns 403).
    """
    async with _client() as c:
        r = await _request_or_raise(
            c, "DELETE", memory_item_absolute_path(memory_id), allow_statuses={403, 404}
        )
        if r.status_code == 404:
            raise ValueError(f"Memory not found: {memory_id}")
        if r.status_code == 403:
            raise ValueError(
                "Cannot delete corporate memories. Use deprecation instead."
            )
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
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("maintain"),
            json={
                "dry_run": dry_run,
                "dedup_threshold": dedup_threshold,
                "normalize_owners": normalize_owners or {},
                "retype_rules": [],
                "fix_superseded_links": fix_superseded_links,
            },
        )
        return r.json()


@mcp.tool()
async def brain_export(ids: list[str]) -> list[dict]:
    """
    Export memories for review or transfer.
    Restricted-sensitivity content is redacted automatically.
    """
    async with _client() as c:
        r = await _request_or_raise(
            c, "POST", memory_absolute_path("export"), json={"ids": ids}
        )
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
    payload = build_sync_check_payload(
        memory_id=memory_id,
        match_key=match_key,
        obsidian_ref=obsidian_ref,
        file_hash=file_hash,
    )
    async with _client() as c:
        r = await _request_or_raise(
            c, "POST", memory_absolute_path("sync_check"), json=payload
        )
        return r.json()


@mcp.tool()
async def brain_obsidian_vaults() -> list[str]:
    """List local Obsidian vaults available to the backend."""
    _require_obsidian_local_tools_enabled()
    adapter = ObsidianCliAdapter()
    try:
        return await adapter.list_vaults()
    except ObsidianCliError as e:
        raise ValueError(str(e))


@mcp.tool()
async def brain_obsidian_read_note(path: str, vault: str = "Documents") -> dict:
    """Read a note from a local Obsidian vault with parsed frontmatter and tags."""
    _require_obsidian_local_tools_enabled()
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
    if not 1 <= limit <= MAX_SYNC_LIMIT:
        raise ValueError(f"limit must be 1–{MAX_SYNC_LIMIT}, got {limit}")
    _require_obsidian_local_tools_enabled()
    adapter = ObsidianCliAdapter()
    try:
        resolved_paths = (
            (paths or [])[:limit]
            if paths
            else await adapter.list_files(vault, folder=folder, limit=limit)
        )
        notes = await asyncio.gather(
            *(adapter.read_note(vault, path) for path in resolved_paths)
        )
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
        r = await _request_or_raise(
            c, "POST", memory_absolute_path("write_many"), json=payload
        )
        result = r.json()
        return {
            "vault": vault,
            "resolved_paths": resolved_paths,
            "scanned": len(resolved_paths),
            "summary": result.get("summary", {}),
            "results": result.get("results", []),
        }


@mcp.tool()
async def brain_obsidian_write_note(
    vault: str,
    path: str,
    content: str,
    title: str | None = None,
    tags: list[str] | None = None,
    frontmatter: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> dict:
    """
    Write a note to Obsidian vault.

    Args:
        vault: Target vault name
        path: Note path (e.g., "Projects/Note.md")
        content: Markdown content
        title: Optional title (added as H1 if provided)
        tags: Optional tags for frontmatter
        frontmatter: Optional additional frontmatter fields
        overwrite: Overwrite existing note
    """
    _require_obsidian_local_tools_enabled()

    # Build full content with title
    full_content = content
    if title:
        full_content = f"# {title}\n\n{content}"

    # Merge frontmatter
    fm = frontmatter or {}
    if tags:
        fm["tags"] = tags
    if title:
        fm["title"] = title

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            "/api/v1/obsidian/write-note",
            json={
                "vault": vault,
                "path": path,
                "content": full_content,
                "frontmatter": fm,
                "overwrite": overwrite,
            },
        )
        return r.json()


@mcp.tool()
async def brain_obsidian_export(
    vault: str,
    folder: str = "OpenBrain Export",
    memory_ids: list[str] | None = None,
    query: str | None = None,
    domain: str | None = None,
    max_items: int = 50,
) -> dict:
    """
    Export memories from OpenBrain to Obsidian notes.

    Args:
        vault: Target vault
        folder: Target folder in vault
        memory_ids: Specific memory IDs to export
        query: Search query to find memories
        domain: Filter by domain (corporate/build/personal)
        max_items: Maximum number of memories to export
    """
    _require_obsidian_local_tools_enabled()

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            "/api/v1/obsidian/export",
            json={
                "vault": vault,
                "folder": folder,
                "memory_ids": memory_ids,
                "query": query,
                "domain": domain,
                "max_items": max_items,
            },
        )
        return r.json()


@mcp.tool()
async def brain_obsidian_collection(
    query: str,
    collection_name: str,
    vault: str = "Documents",
    folder: str = "Collections",
    domain: str | None = None,
    max_items: int = 50,
    group_by: str | None = None,
) -> dict:
    """
    Create a collection (index note) from OpenBrain memories.

    Creates a single index note with links to exported memory notes.

    Args:
        query: Search query
        collection_name: Name for the collection
        vault: Target vault
        folder: Target folder
        domain: Filter by domain
        max_items: Maximum memories
        group_by: How to group (entity_type, owner, tags)
    """
    if not 1 <= max_items <= MAX_SYNC_LIMIT:
        raise ValueError(f"max_items must be 1–{MAX_SYNC_LIMIT}, got {max_items}")
    _require_obsidian_local_tools_enabled()

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            "/api/v1/obsidian/collection",
            json={
                "query": query,
                "collection_name": collection_name,
                "vault": vault,
                "folder": folder,
                "domain": domain,
                "max_items": max_items,
                "group_by": group_by,
            },
        )
        return r.json()


@mcp.tool()
async def brain_store_bulk(items: list[dict[str, Any]]) -> dict:
    """Bulk store memories. Use for archiving or synchronization."""
    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("write_many"),
            json={"records": items, "write_mode": "upsert"},
        )
        return r.json()


@mcp.tool()
async def brain_upsert_bulk(items: list[dict[str, Any]]) -> dict:
    """Idempotent bulk synchronization using match_key."""
    async with _client() as c:
        r = await _request_or_raise(
            c, "POST", memory_absolute_path("bulk_upsert"), json=items
        )
        return r.json()


@mcp.tool()
async def brain_obsidian_bidirectional_sync(
    vault: str = "Memory",
    strategy: str = "domain_based",
    dry_run: bool = False,
) -> dict:
    """
    Bidirectional sync between OpenBrain and Obsidian.

    Detects and resolves changes in both systems.

    Args:
        vault: Target vault name
        strategy: Conflict resolution strategy (last_write_wins, domain_based, manual_review)
        dry_run: If True, only detect changes without applying

    Returns:
        Sync result with detected changes, conflicts, and applied updates.
    """
    _require_obsidian_local_tools_enabled()

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            "/api/v1/obsidian/bidirectional-sync",
            json={
                "vault": vault,
                "strategy": strategy,
                "dry_run": dry_run,
            },
        )
        return r.json()


@mcp.tool()
async def brain_obsidian_sync_status() -> dict:
    """
    Get bidirectional sync status.

    Returns statistics about tracked items and sync state.
    """
    _require_obsidian_local_tools_enabled()

    async with _client() as c:
        r = await _request_or_raise(c, "GET", "/api/v1/obsidian/sync-status")
        return r.json()


@mcp.tool()
async def brain_obsidian_update_note(
    vault: str,
    path: str,
    content: str | None = None,
    append: bool = False,
    tags: list[str] | None = None,
) -> dict:
    """
    Update an existing note in Obsidian.

    Args:
        vault: Target vault name
        path: Note path
        content: New content (or content to append if append=True)
        append: If True, append to existing content
        tags: Tags to update in frontmatter
    """
    _require_obsidian_local_tools_enabled()

    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            "/api/v1/obsidian/update-note",
            json={
                "vault": vault,
                "path": path,
                "content": content,
                "append": append,
                "tags": tags,
            },
        )
        return r.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
