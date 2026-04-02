# OpenBrain Unified Architecture

## Module boundaries

The unified service is split into narrow modules with explicit responsibilities.

- `unified/src/main.py`
  Builds the FastAPI app, defines access-control helpers, exposes handler symbols used by tests, and registers routes.
- `unified/src/app_factory.py`
  Creates the FastAPI application instance.
- `unified/src/middleware.py`
  Owns request tracing and HTTP metrics middleware.
- `unified/src/lifespan.py`
  Owns startup/shutdown behavior, telemetry restore/flush, and embedding client shutdown.
- `unified/src/routes_v1.py`
  Registers canonical V1 and discovery routes.
- `unified/src/routes_ops.py`
  Registers health and operational endpoints.
- `unified/src/routes_crud.py`
  Registers legacy CRUD and admin endpoints.
- `unified/src/memory_reads.py`
  Owns reads, search, export, sync-check, maintenance report reads, and grounding-pack synthesis.
- `unified/src/memory_writes.py`
  Owns create/update/delete/upsert flows and maintenance mutations.
- `unified/src/telemetry_store.py`
  Persists counters and histograms.
- `unified/src/crud_common.py`
  Holds shared model mapping, export policy, tenant filtering, governance helpers, and audit helpers.
- `unified/src/crud.py`
  Compatibility facade for older imports and test monkey-patching. New runtime code should not depend on it.

## Routing model

Route registration is centralized in `main.py`, but route declarations live in dedicated registration modules.

- Keep handlers importable from `main.py` while tests still patch `main.<handler>`.
- New endpoints should be added by:
  1. implementing the handler in the most specific module or in `main.py` if it still depends on shared access-control helpers
  2. registering the route in one of the `routes_*.py` modules
  3. adding regression coverage for both handler behavior and route contract where relevant

## CRUD model

The cleanup intentionally separates read and write paths.

- Put query-only logic in `memory_reads.py`.
- Put mutating logic in `memory_writes.py`.
- Put shared pure helpers in `crud_common.py`.
- Do not add new business logic to `crud.py` unless the goal is backward compatibility.

## Transport contract

HTTP MCP transport and stdio gateway must expose the same logical record shape.

- Shared schema drift should be treated as a regression.
- Transport parity tests are required for:
  - `brain_get`
  - `brain_find`
  - `brain_store`
  - `brain_update`

## Testing rules

- Prefer testing focused modules directly.
- Keep compatibility tests for `main.py` and `crud.py` only where they protect public API stability.
- Use full regression discovery in CI in addition to targeted smoke tests.
- If a refactor needs monkey-patching compatibility, preserve it deliberately and document why.

## Operational rules

- Public-mode safety must stay fail-closed.
- Secret scanning and compose guardrails are required checks, not optional hygiene.
- Telemetry persistence must remain transactional and lifecycle-safe.
