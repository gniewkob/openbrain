# ADR-0001: Architecture Baseline and Module Ownership

- Status: Accepted
- Date: 2026-04-08
- Owners: OpenBrain maintainers

## Context

OpenBrain has grown across multiple refactors and now contains strong domain logic plus multiple integration surfaces. The main risk is not missing functionality, but unclear ownership boundaries between domain logic, transports, API handlers, and compatibility code.

When module responsibilities are ambiguous, regressions appear as contract drift (for example, capability mismatches) rather than obvious runtime failures.

## Decision

OpenBrain adopts a lightweight layered model:

1. `domain/core`: business behavior and invariants
2. `governance`: access control and audit semantics
3. `application`: use-case orchestration (to be expanded in follow-up PRs)
4. `adapters`: transport and external integration mapping
5. `platform`: app assembly, lifecycle, middleware, telemetry
6. `compatibility`: legacy bridges and migration-only code paths

## Module ownership map

| Layer | Primary modules | Responsibility |
|---|---|---|
| domain/core | `unified/src/memory_reads.py`, `unified/src/memory_writes.py`, `unified/src/crud_common.py` | Memory behavior, lineage, search/export/sync-check, write modes |
| governance | `unified/src/security/policy.py`, auth actor resolution in V1 handlers | Domain access policy, owner/tenant scope, admin gates, audit actor semantics |
| application | (new use-case layer in follow-up PRs) | Stable orchestration boundary for store/update/search/context/sync/export |
| adapters | `unified/src/api/v1/*.py`, `unified/mcp-gateway/src/main.py`, `unified/src/common/obsidian_adapter.py`, `unified/src/services/converter.py`, `unified/src/obsidian_sync.py` | I/O mapping, protocol conversion, external system integration |
| platform | `unified/src/main.py`, `unified/src/app_factory.py`, `unified/src/routes_*.py`, `unified/src/middleware.py`, `unified/src/lifespan.py` | App wiring, route registration, startup/shutdown, middleware/metrics |
| compatibility | `unified/src/crud.py`, selected legacy path handling | Backward compatibility only; no new business logic |

## Rules

- New business logic must not be added to compatibility modules.
- Transport adapters must not own governance policy decisions.
- Endpoint handlers should validate/authorize and delegate, not implement domain behavior directly.
- Sync remains an integration context; it should not become implicit CRUD behavior.

## Consequences

- Refactors can be incremental without changing public contracts.
- Drift between adapters becomes testable and visible.
- Follow-up use-case extraction has a stable target boundary.

