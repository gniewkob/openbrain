# ADR-0002: Canonical MCP Transport and Compatibility Posture

- Status: Accepted
- Date: 2026-04-08
- Owners: OpenBrain maintainers

## Context

The repository currently exposes MCP functionality through:

- `unified/mcp-gateway/src/main.py` (dedicated stdio gateway)
- `unified/src/mcp_transport.py` (HTTP MCP transport)

Both paths are useful, but treating both as equal product surfaces causes contract drift, duplicated fixes, and inconsistent capability reporting.

## Decision

`unified/mcp-gateway/src/main.py` is the canonical MCP product surface.

`unified/src/mcp_transport.py` is a compatibility transport. It remains supported for now but is not the primary path for new MCP features.

## Scope of parity

Required parity between canonical and compatibility transport:

- core logical record shape for `store/get/search/update`
- capability structure consistency at high level (tier structure + explicit Obsidian status)
- consistent error framing for transport-facing failures

Explicitly not required as strict parity:

- full local-only Obsidian tool surface
- identical operational diagnostics internals

## Rules

- New MCP features are implemented in the canonical gateway first.
- Adding new behavior directly to `mcp_transport.py` requires explicit justification.
- Capability fields must be documented as transport-scoped when they are transport-specific.
- Compatibility transport regressions are fixed, but architectural expansion happens in the canonical gateway.

## Migration posture

- Keep compatibility transport stable while use-case extraction proceeds.
- Re-evaluate long-term need for `mcp_transport.py` after use-case layer migration and transport drift metrics are reviewed.

## Consequences

- Reduces long-term drift and duplicate implementation effort.
- Clarifies where ownership and review focus should be for MCP behavior.
- Preserves current compatibility while allowing deliberate deprecation decisions later.

