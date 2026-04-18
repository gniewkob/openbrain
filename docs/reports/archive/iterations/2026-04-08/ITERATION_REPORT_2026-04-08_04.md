# Iteration Report 2026-04-08 / 04

## Problem

The codebase had no explicit architectural decision record for module ownership boundaries and no explicit canonical MCP transport decision, which made drift likely during future refactors.

## Evidence

- Existing architecture docs described modules, but did not freeze ownership as accepted decisions.
- Two MCP-facing transport implementations existed without a canonical/compatibility posture.
- Recent fixes had to be applied in multiple places to avoid divergence.

## Decision

- Introduce formal ADRs:
  - `ADR-0001`: architecture baseline and module ownership map.
  - `ADR-0002`: canonical MCP transport and compatibility posture.
- Link ADRs from architecture-facing documentation for discoverability.

## Risk

- ADRs reduce ambiguity but do not themselves migrate runtime behavior.
- Follow-up implementation PRs are still required for use-case extraction and transport cleanup.

## Status

- Architecture ownership baseline: `fixed`
- Canonical MCP transport decision: `fixed`
- Runtime migration to use-case layer: `deferred`
