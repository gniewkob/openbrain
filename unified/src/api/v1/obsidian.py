"""V1 Obsidian API endpoints."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import require_auth
from ...common.obsidian_adapter import ObsidianCliAdapter, ObsidianCliError
from ...db import get_session
from ...memory_reads import get_memory, search_memories
from ...obsidian_cli import note_to_memory_write_record
from ...obsidian_sync import (
    BidirectionalSyncEngine,
    ObsidianChangeTracker,
    SyncStrategy,
)
from ...use_cases.memory import store_memories_many as handle_memory_write_many
from ...schemas import (
    MemoryWriteManyRequest,
    WriteMode,
    ObsidianBidirectionalSyncRequest,
    ObsidianBidirectionalSyncResponse,
    ObsidianCollectionRequest,
    ObsidianCollectionResponse,
    MemoryOut,
    ObsidianExportItem,
    ObsidianExportRequest,
    ObsidianExportResponse,
    ObsidianReadRequest,
    ObsidianNoteResponse,
    ObsidianSyncChange,
    ObsidianSyncRequest,
    ObsidianSyncResponse,
    ObsidianSyncStatus,
    ObsidianWriteRequest,
    ObsidianWriteResponse,
    SearchRequest,
)
from ...services.converter import (
    build_collection_index,
    memory_to_frontmatter,
    memory_to_note_content,
    sanitize_filename,
)

# Import from main for now - will be moved to security module later
from ...security import require_admin

router = APIRouter(prefix="/obsidian", tags=["obsidian"])

# Sync singletons
_sync_tracker: ObsidianChangeTracker | None = None
_sync_engine: BidirectionalSyncEngine | None = None
_sync_lock = asyncio.Lock()


async def _get_sync_tracker() -> ObsidianChangeTracker:
    """Get or create sync tracker singleton."""
    global _sync_tracker
    if _sync_tracker is None:
        async with _sync_lock:
            if _sync_tracker is None:
                _sync_tracker = ObsidianChangeTracker()
    return _sync_tracker


async def _get_sync_engine(strategy: str = "domain_based") -> BidirectionalSyncEngine:
    """Get or create sync engine singleton."""
    global _sync_engine
    if _sync_engine is None:
        async with _sync_lock:
            if _sync_engine is None:
                strategy_enum = SyncStrategy(strategy)
                _sync_engine = BidirectionalSyncEngine(
                    strategy=strategy_enum,
                    tracker=await _get_sync_tracker(),
                )
    return _sync_engine


@router.get("/vaults")
async def v1_obsidian_vaults(
    _user: dict[str, Any] = Depends(require_auth),
) -> list[str]:
    """List available Obsidian vaults."""
    require_admin(_user)
    adapter = ObsidianCliAdapter()
    try:
        return await adapter.list_vaults()
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/read-note")
async def v1_obsidian_read_note(
    req: ObsidianReadRequest,
    _user: dict[str, Any] = Depends(require_auth),
) -> ObsidianNoteResponse:
    """Read a note from Obsidian vault."""
    require_admin(_user)
    adapter = ObsidianCliAdapter()
    try:
        note = await adapter.read_note(req.vault, req.path)
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return ObsidianNoteResponse(
        vault=note.vault,
        path=note.path,
        title=note.title,
        content=note.content,
        frontmatter=note.frontmatter,
        tags=note.tags,
        file_hash=note.file_hash,
    )


@router.post("/sync")
async def v1_obsidian_sync(
    req: ObsidianSyncRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict[str, Any] = Depends(require_auth),
) -> ObsidianSyncResponse:
    """Sync notes from Obsidian to OpenBrain."""
    require_admin(_user)
    adapter = ObsidianCliAdapter()
    try:
        if req.paths:
            resolved_paths = req.paths[: req.limit]
        else:
            resolved_paths = await adapter.list_files(
                req.vault, folder=req.folder, limit=req.limit
            )

        notes = await asyncio.gather(
            *(adapter.read_note(req.vault, path) for path in resolved_paths)
        )
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))
    records = [
        note_to_memory_write_record(
            note,
            default_domain=req.domain,
            default_entity_type=req.entity_type,
            default_owner=req.owner,
            default_tags=req.tags,
        )
        for note in notes
    ]
    result = await handle_memory_write_many(
        session,
        MemoryWriteManyRequest(records=records, write_mode=WriteMode.upsert),
        actor=_user.get("sub", "obsidian-sync"),
    )
    return ObsidianSyncResponse(
        vault=req.vault,
        resolved_paths=resolved_paths,
        scanned=len(resolved_paths),
        summary=result.summary,
        results=result.results,
    )


@router.post("/write-note")
async def v1_obsidian_write_note(
    req: ObsidianWriteRequest,
    _user: dict[str, Any] = Depends(require_auth),
) -> ObsidianWriteResponse:
    """Write a single note to Obsidian vault."""
    require_admin(_user)
    adapter = ObsidianCliAdapter()
    try:
        # Check if note exists
        exists = await adapter.note_exists(req.vault, req.path)

        note = await adapter.write_note(
            vault=req.vault,
            path=req.path,
            content=req.content,
            frontmatter=req.frontmatter,
            overwrite=req.overwrite,
        )
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))

    return ObsidianWriteResponse(
        vault=note.vault,
        path=note.path,
        title=note.title,
        content=note.content,
        frontmatter=note.frontmatter,
        tags=note.tags,
        file_hash=note.file_hash,
        created=not exists,  # True if new, False if updated
    )


@router.post("/export")
async def v1_obsidian_export(
    req: ObsidianExportRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict[str, Any] = Depends(require_auth),
) -> ObsidianExportResponse:
    """Export memories from OpenBrain to Obsidian notes."""
    require_admin(_user)

    # Get memories to export
    memories: list[MemoryOut] = []
    if req.memory_ids:
        for mid in req.memory_ids:
            mem = await get_memory(session, mid)
            if mem:
                memories.append(mem)
    elif req.query:
        search_results = await search_memories(
            session,
            SearchRequest(query=req.query, top_k=req.max_items, filters={}),
        )
        memories = [mem for mem, _ in search_results]

        # Filter by domain if specified
        if req.domain:
            memories = [m for m in memories if m.domain == req.domain]
    else:
        raise HTTPException(
            status_code=422, detail="Either memory_ids or query must be provided"
        )

    # Export to Obsidian
    import structlog

    log = structlog.get_logger()
    adapter = ObsidianCliAdapter()
    exported: list[Any] = []
    errors: list[dict[str, str]] = []

    for memory in memories:
        try:
            # Generate note path
            safe_title = sanitize_filename(memory.title or memory.id)
            path = f"{req.folder}/{safe_title}.md" if req.folder else f"{safe_title}.md"

            # Generate content and frontmatter
            content = memory_to_note_content(memory, req.template)
            frontmatter = memory_to_frontmatter(memory)

            # Check if exists
            exists = await adapter.note_exists(req.vault, path)

            note = await adapter.write_note(
                vault=req.vault,
                path=path,
                content=content,
                frontmatter=frontmatter,
                overwrite=True,
            )
            exported.append(
                ObsidianExportItem(
                    memory_id=memory.id,
                    path=note.path,
                    title=note.title,
                    created=not exists,
                )
            )
        except Exception as e:
            log.warning("export_memory_failed", memory_id=memory.id, error=str(e))
            errors.append({"memory_id": memory.id, "error": str(e)})

    return ObsidianExportResponse(
        vault=req.vault,
        folder=req.folder,
        exported_count=len(exported),
        exported=exported,
        errors=errors,
    )


@router.post("/collection")
async def v1_obsidian_collection(
    req: ObsidianCollectionRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict[str, Any] = Depends(require_auth),
) -> ObsidianCollectionResponse:
    """Create a collection (index note) from memories."""
    require_admin(_user)

    # Get memories for grouping info
    search_results = await search_memories(
        session,
        SearchRequest(query=req.query, top_k=req.max_items, filters={}),
    )
    memories = [mem for mem, _ in search_results]
    if req.domain:
        memories = [m for m in memories if m.domain == req.domain]

    # Export memories first
    export_req = ObsidianExportRequest(
        vault=req.vault,
        folder=f"{req.folder}/{req.collection_name}",
        query=req.query,
        domain=req.domain,
        max_items=req.max_items,
    )

    # Call export (we need to import the function)
    from ...api.v1.obsidian import v1_obsidian_export

    export_result = await v1_obsidian_export(export_req, session, _user)

    # Create index note
    adapter = ObsidianCliAdapter()
    try:
        index_content = build_collection_index(
            collection_name=req.collection_name,
            query=req.query,
            exported=export_result.exported,
            memories=memories,
            group_by=req.group_by,
        )

        index_path = f"{req.folder}/{req.collection_name}/Index.md"

        await adapter.write_note(
            vault=req.vault,
            path=index_path,
            content=index_content,
            frontmatter={
                "title": req.collection_name,
                "tags": ["openbrain-collection", "index"],
                "query": req.query,
                "item_count": len(export_result.exported),
            },
            overwrite=True,
        )

        return ObsidianCollectionResponse(
            collection_name=req.collection_name,
            vault=req.vault,
            folder=req.folder,
            index_path=index_path,
            exported_count=export_result.exported_count,
            exported=export_result.exported,
            errors=export_result.errors,
        )
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/bidirectional-sync")
async def v1_obsidian_bidirectional_sync(
    req: ObsidianBidirectionalSyncRequest,
    session: AsyncSession = Depends(get_session),
    _user: dict[str, Any] = Depends(require_auth),
) -> ObsidianBidirectionalSyncResponse:
    """Perform bidirectional synchronization between OpenBrain and Obsidian."""
    require_admin(_user)

    engine = await _get_sync_engine(req.strategy)
    adapter = ObsidianCliAdapter()

    timeout_s = float(os.environ.get("OBSIDIAN_SYNC_TIMEOUT_S", "120"))
    try:
        async with asyncio.timeout(timeout_s):
            result = await engine.sync(
                session=session,
                adapter=adapter,
                vault=req.vault,
                dry_run=req.dry_run,
            )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="Obsidian sync timed out")

    # Convert to response format
    changes_response = [
        ObsidianSyncChange(
            memory_id=change.memory_id,
            obsidian_path=change.obsidian_path,
            change_type=change.change_type.value,
            source=change.source,
            conflict=change.conflict,
            resolution=change.resolution,
        )
        for change in result.details
    ]

    return ObsidianBidirectionalSyncResponse(
        started_at=result.started_at,
        completed_at=result.completed_at,
        vault=req.vault,
        strategy=req.strategy,
        changes_detected=result.changes_detected,
        changes_applied=result.changes_applied,
        conflicts=result.conflicts,
        dry_run=req.dry_run,
        errors=result.errors,
        changes=changes_response,
    )


@router.get("/sync-status")
async def v1_obsidian_sync_status(
    _user: dict[str, Any] = Depends(require_auth),
) -> ObsidianSyncStatus:
    """Get status of sync tracking."""
    require_admin(_user)

    tracker = await _get_sync_tracker()
    stats = tracker.get_stats()

    return ObsidianSyncStatus(**stats)


@router.post("/update-note")
async def v1_obsidian_update_note(
    vault: str,
    path: str,
    content: str | None = None,
    append: bool = False,
    tags: list[str] | None = None,
    _user: dict[str, Any] = Depends(require_auth),
) -> ObsidianWriteResponse:
    """Update an existing note in Obsidian."""
    require_admin(_user)

    adapter = ObsidianCliAdapter()

    # Build frontmatter update if tags provided
    frontmatter = None
    if tags:
        frontmatter = {"tags": tags}

    try:
        note = await adapter.update_note(
            vault=vault,
            path=path,
            content=content,
            frontmatter=frontmatter,
            append=append,
        )

        return ObsidianWriteResponse(
            vault=note.vault,
            path=note.path,
            title=note.title,
            content=note.content,
            frontmatter=note.frontmatter,
            tags=note.tags,
            file_hash=note.file_hash,
            created=False,  # Always updating
        )
    except ObsidianCliError as e:
        raise HTTPException(status_code=503, detail=str(e))
