# Operational Report: 2026-03-31

## Scope

This report captures the 2026-03-31 hardening session for OpenBrain Unified.
It covers authorization closure for `export` / `sync-check`, local gateway trust-boundary tightening,
default ingress posture changes, request bounds, access-denied telemetry, and the `tenant_id` schema promotion.

## Changes Completed

### 1. Record-level authorization closure

- `export` now validates every requested record through the same record-level access gates used by normal reads.
- `sync-check` now checks access after lookup and masks unauthorized records as `404`.
- Regression tests were added for cross-scope denial.

Files:
- `unified/src/main.py`
- `unified/tests/test_access_control.py`

### 2. Local gateway trust boundary tightening

- Local `brain_obsidian_vaults`, `brain_obsidian_read_note`, and `brain_obsidian_sync` are now disabled by default.
- They require explicit opt-in with `ENABLE_LOCAL_OBSIDIAN_TOOLS=1`.
- `brain_capabilities` now advertises those tools only when the flag is enabled.

Files:
- `unified/mcp-gateway/src/main.py`
- `unified/mcp-gateway/tests/test_obsidian_tools.py`
- `INSTALLATION.md`

### 3. Default-local ingress posture

- `ngrok` was moved into the Compose `public` profile.
- `./start_unified.sh start` now starts a local-only stack by default.
- External exposure requires explicit `ENABLE_NGROK=1`.
- Runtime status output was updated to show when the public profile is disabled.

Files:
- `docker-compose.unified.yml`
- `start_unified.sh`
- `.env.example`
- `INSTALLATION.md`
- `docs/operating-manual.md`

### 4. Request bounds

- Added hard limits for:
  - `SearchRequest.top_k`
  - `MemoryFindRequest.limit`
  - `MemoryGetContextRequest.max_items`
  - `ObsidianSyncRequest.limit`
  - `ExportRequest.ids`
  - content length, tags, `match_key`, `tenant_id`, and path-like fields
- Added validation tests to prevent silent contract drift.

Files:
- `unified/src/schemas.py`
- `unified/tests/test_request_bounds.py`

### 5. Access-denied telemetry

- Added Prometheus counters:
  - `access_denied_total`
  - `access_denied_admin_total`
  - `access_denied_domain_total`
  - `access_denied_owner_total`
  - `access_denied_tenant_total`
- Wired counters into central authorization and scope-enforcement helpers.

Files:
- `unified/src/telemetry.py`
- `unified/src/main.py`
- `unified/tests/test_metrics.py`

### 6. `tenant_id` schema promotion

- Added first-class indexed `tenant_id` column on `memories`.
- Added Alembic migration to backfill from legacy `metadata -> tenant_id`.
- Updated CRUD reads/writes to prefer the column and fall back to metadata for compatibility.
- Kept metadata mirroring so old callers and old records remain compatible during transition.

Files:
- `unified/src/models.py`
- `unified/src/crud.py`
- `unified/migrations/versions/004_add_tenant_id_column.py`
- `unified/tests/test_metadata_lineage.py`

## Verification

Passed:
- backend: `125 passed`
- gateway: `10 tests OK`
- `python3 -m py_compile` on touched backend and gateway files
- `docker compose -f docker-compose.unified.yml config`

Live runtime checks:
- stack restarted successfully
- Alembic migration applied and `memories.tenant_id` exists with index `ix_memories_tenant_id`
- `./start_unified.sh status` shows local-only mode by default

## Operational Notes

- To enable the public tunnel explicitly:

```bash
ENABLE_NGROK=1 ./start_unified.sh start
```

- To enable local Obsidian tools in the stdio gateway explicitly:

```bash
ENABLE_LOCAL_OBSIDIAN_TOOLS=1
```

## Current Residual Risks

- Telemetry remains in-memory and per-process; multi-worker deployments still need a shared backend.
- Embedding requests still create fresh HTTP clients and do not batch/cache aggressively.
- `main.py` and `crud.py` remain structurally large and should still be split over time.
