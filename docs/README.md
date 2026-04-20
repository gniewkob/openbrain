# API Architecture: OpenBrain Unified

OpenBrain Unified v2.1 uses a tiered architecture to manage knowledge across different life domains while maintaining strict data integrity.

## Canonical Data Model: `MemoryRecord`

The core of the system is the `MemoryRecord`, a standardized object that includes:
- **Domain**: `corporate`, `build`, or `personal`.
- **Match Key**: A unique identifier for idempotent synchronization.
- **Governance**: Automatic versioning for corporate data.
- **Metadata**: Title, tags, relations, and source tracking.

## API Versions

### V1 (Canonical Platform)
Located under `/api/v1/memory/`. This is the recommended path for all new integrations.
- `POST /write`: Unified engine for creates and updates.
- `POST /write-many`: Optimized batch processing.
- `POST /find`: Hybrid semantic + structured search.
- `POST /get-context`: Intelligent grounding pack for LLMs.

### Legacy CRUD (Deprecated)
Located under `/api/memories/`. Maintained for backward compatibility but maps internally to the V1 engine.

## Write Modes
OpenBrain supports several explicit write modes to prevent accidental data loss:
- `upsert`: Default mode. Updates existing records by `match_key` or creates new ones.
- `append_version`: Always creates a new version, linking it to the previous record.
- `create_only`: Fails if a record with the same `match_key` already exists.

## Security
- **Local**: Unauthenticated access on port 7010.
- **Remote**: Mandatory OIDC (Auth0) authentication when `PUBLIC_MODE=true`.
- **System**: Internal calls between MCP and REST use `X-Internal-Key`.

## Architecture Decisions

- [ADR-0001: Architecture Baseline and Module Ownership](./architecture/adr/ADR-0001-architecture-baseline.md)
- [ADR-0002: Canonical MCP Transport and Compatibility Posture](./architecture/adr/ADR-0002-canonical-mcp-transport.md)

## Current Status

- [Status 2026-04-14](./reports/status/STATUS_2026-04-14.md) — **100% test coverage, 1403 tests, ngrok active**
- [Improvement Roadmap Q2 2026](./architecture/roadmap.md)

## Iteration Tracking (2026-04-08)

- [Iteration Synthesis](./reports/iterations/ITERATION_SYNTHESIS_2026-04-08.md)
- [Iteration Reports Index](./reports/iterations/ITERATION_REPORTS_INDEX_2026-04-08.md)
- [Cleanup Register](./reports/iterations/CLEANUP_REGISTER_2026-04-08.md)
- [Merge Readiness Snapshot](./reports/iterations/MERGE_READINESS_2026-04-08.md)

## Archive

- [Iteration Archive](./reports/archive/iterations/2026-04-08/)
- [Legacy Docs Archive](./reports/archive/legacy/2026-04-07/README.md)
