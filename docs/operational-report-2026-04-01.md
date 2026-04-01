# Operational Report: 2026-04-01

## Scope

This report captures the 2026-04-01 audit remediation session for OpenBrain Unified.
It covers write-path correctness, telemetry durability, metrics accuracy, MCP log redaction,
OIDC concurrency safety, and the regression test coverage added for those areas.

## Changes Completed

### 1. Metadata-aware idempotent writes

- `handle_memory_write()` no longer treats metadata-only changes as `skipped` when `content_hash` is unchanged.
- The skip decision now compares the effective persisted state, including:
  - `tenant_id`
  - `title`
  - `entity_type`
  - `relations`
  - `custom_fields`
  - `source`
  - existing fields already covered before (`owner`, `tags`, `obsidian_ref`, `sensitivity`)
- This closes a silent data-loss path where valid update requests could be ignored.

Files:
- `unified/src/crud.py`
- `unified/tests/test_audit_fixes.py`

### 2. Durable telemetry state

- Telemetry persistence now stores both counters and histograms.
- Flushes are written in a single transaction per sync cycle instead of one commit per counter.
- Startup now restores histogram state as well as counters.
- Added a new Alembic migration and model for `telemetry_histograms`.

Files:
- `unified/src/telemetry.py`
- `unified/src/crud.py`
- `unified/src/main.py`
- `unified/src/models.py`
- `unified/migrations/versions/006_add_telemetry_histograms_table.py`
- `unified/tests/test_metrics.py`

### 3. Metrics middleware accuracy

- `MetricsMiddleware` now records request duration and HTTP status metrics even when the handler raises an unhandled exception.
- Exception paths are counted as `500` instead of disappearing from telemetry.

Files:
- `unified/src/main.py`
- `unified/tests/test_metrics.py`

### 4. MCP transport log redaction

- MCP HTTP logging now redacts:
  - `content`
  - `title`
  - `tenant_id`
  - `match_key`
  - `obsidian_ref`
  - `custom_fields`
- This reduces the chance of leaking tenant metadata, private references, or structured sensitive payloads into log sinks.

Files:
- `unified/src/mcp_transport.py`
- `unified/tests/test_mcp_transport.py`

### 5. OIDC verifier loop safety

- `OIDCVerifier` now creates its refresh lock lazily instead of at import time.
- This removes the import-time event-loop binding risk in multi-loop contexts and test reload scenarios.

Files:
- `unified/src/auth.py`
- `unified/tests/test_auth_security.py`

## Verification

Passed:
- `python3 -m py_compile` on touched backend, tests, and migration files
- container build and stack restart via `./start_unified.sh start`
- targeted regression test suite inside the application container:

```bash
docker exec -e PUBLIC_MODE=false -e PUBLIC_BASE_URL= openbrain-unified-server \
  python -m unittest \
    tests.test_audit_fixes \
    tests.test_auth_security \
    tests.test_mcp_transport \
    tests.test_metrics
```

Result:
- `Ran 50 tests ... OK`

Operational notes:
- the first draft of migration `006` failed because the Alembic revision ID exceeded the width of `alembic_version.version_num`
- the revision ID was shortened and the stack was rebuilt successfully

## Current Residual Risks

- Telemetry is now durable across restarts for a single instance, but it is still not a cross-worker/shared aggregation design.
- `main.py` and `crud.py` remain large and continue to deserve structural decomposition.
- MCP transport still creates a fresh `httpx.AsyncClient` per request; this is acceptable for now, but not ideal if transport traffic rises materially.
