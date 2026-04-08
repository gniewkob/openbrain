"""Memory application use-cases.

The goal is to provide a stable orchestration boundary for API and transport
adapters while preserving current runtime behavior.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ..memory_reads import find_memories_v1, get_grounding_pack
from ..memory_writes import (
    delete_memory as delete_memory_write,
    handle_memory_write,
    handle_memory_write_many,
    run_maintenance as run_maintenance_write,
    upsert_memories_bulk as upsert_memories_bulk_write,
    update_memory as update_memory_write,
)
from ..schemas import (
    BulkUpsertResult,
    MaintenanceReport,
    MaintenanceRequest,
    MemoryFindRequest,
    MemoryGetContextRequest,
    MemoryGetContextResponse,
    MemoryOut,
    MemoryUpsertItem,
    MemoryUpdate,
    MemoryWriteManyRequest,
    MemoryWriteManyResponse,
    MemoryWriteRequest,
    MemoryWriteResponse,
)


async def store_memory(
    session: AsyncSession,
    req: MemoryWriteRequest,
    *,
    actor: str,
) -> MemoryWriteResponse:
    """Create or update memory through the canonical V1 write engine."""
    return await handle_memory_write(session, req, actor=actor)


async def store_memories_many(
    session: AsyncSession,
    req: MemoryWriteManyRequest,
    *,
    actor: str,
) -> MemoryWriteManyResponse:
    """Create or update multiple memories through the canonical V1 write engine."""
    return await handle_memory_write_many(session, req, actor=actor)


async def update_memory(
    session: AsyncSession,
    memory_id: str,
    data: MemoryUpdate,
    *,
    actor: str,
) -> MemoryOut | None:
    """Update memory with domain-aware semantics (versioned for corporate)."""
    return await update_memory_write(session, memory_id, data, actor=actor)


async def delete_memory(
    session: AsyncSession,
    memory_id: str,
    *,
    actor: str,
) -> bool:
    """Delete memory where policy permits hard-delete."""
    return await delete_memory_write(session, memory_id, actor=actor)


async def run_maintenance(
    session: AsyncSession,
    req: MaintenanceRequest,
    *,
    actor: str,
) -> MaintenanceReport:
    """Run maintenance via the canonical write-side maintenance engine."""
    return await run_maintenance_write(session, req, actor=actor)


async def upsert_memories_bulk(
    session: AsyncSession,
    items: list[MemoryUpsertItem],
) -> BulkUpsertResult:
    """Bulk upsert through the canonical write-side bulk engine."""
    return await upsert_memories_bulk_write(session, items)


async def search_memories(
    session: AsyncSession,
    req: MemoryFindRequest,
):
    """Find memories using semantic + structured V1 search."""
    return await find_memories_v1(session, req)


async def get_memory_context(
    session: AsyncSession,
    req: MemoryGetContextRequest,
    *,
    owner: str | None = None,
    tenant_id: str | None = None,
) -> MemoryGetContextResponse:
    """Build grounding/context pack for LLM-facing queries."""
    return await get_grounding_pack(session, req, owner=owner, tenant_id=tenant_id)
