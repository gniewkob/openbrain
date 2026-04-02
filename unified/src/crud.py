"""
Compatibility facade for the unified memory service.

Runtime code should prefer the focused modules introduced during cleanup:
- `memory_reads.py` for read/search/export/reporting paths
- `memory_writes.py` for write/update/delete/maintenance paths
- `telemetry_store.py` for persisted telemetry state
- `crud_common.py` for shared mapping/policy helpers

This module is intentionally kept as a thin re-export layer so existing tests,
legacy imports, and targeted monkey-patches continue to work while the rest of
the codebase migrates to the narrower modules.
"""
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .crud_common import (
    CORPORATE,
    EXPORT_POLICY,
    STATUS_ACTIVE,
    STATUS_DUPLICATE,
    STATUS_SUPERSEDED,
    _audit,
    _can_hard_delete,
    _export_record,
    _record_matches_existing,
    _requires_append_only,
    _tenant_filter_expr,
    _to_out,
    _to_record,
)
from .memory_reads import (
    export_memories,
    find_memories_v1,
    get_grounding_pack,
    get_memory,
    get_memory_as_record,
    get_memory_domain_status_counts,
    get_memory_raw,
    get_memory_status_counts,
    get_maintenance_report,
    list_maintenance_reports,
    list_memories,
    search_memories,
    sync_check,
)
from .memory_writes import (
    delete_memory,
    handle_memory_write,
    handle_memory_write_many,
    run_maintenance,
    store_memories_bulk,
    store_memory,
    update_memory,
    upsert_memories_bulk,
)
from .embed import get_embedding
from .models import DomainEnum, Memory
from .schemas import (
    BulkUpsertResult,
    MaintenanceReport,
    MaintenanceReportDetail,
    MaintenanceReportEntry,
    MaintenanceRequest,
    MemoryCreate,
    MemoryFindRequest,
    MemoryGetContextRequest,
    MemoryGetContextResponse,
    MemoryOut,
    MemoryRecord,
    MemoryUpdate,
    MemoryUpsertItem,
    MemoryWriteManyRequest,
    MemoryWriteManyResponse,
    MemoryWriteRequest,
    MemoryWriteResponse,
    SearchRequest,
    SearchResult,
)
from .telemetry_store import (
    get_telemetry_counters,
    get_telemetry_histograms,
    upsert_telemetry_metrics,
)

log = structlog.get_logger()
