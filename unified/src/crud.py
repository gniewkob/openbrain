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


import structlog


log = structlog.get_logger()
