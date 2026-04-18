# Iteration Report 47 (2026-04-08)

## Stream
- Governance + observability backlog closure (post-PR stabilization)

## Problem
- Governance backlog still had open items for:
  - shared telemetry counter backend in multi-worker mode,
  - explicit policy tests for update semantics per domain.
- Corporate store invariants in gateway were not explicitly enforced at input boundary (`owner`, `match_key`).

## Evidence
- `docs/governance-layer.md` backlog section still listed items 1 and 3 as open.
- Gateway path tests covered general store/update behavior but did not lock corporate write contract strongly enough.
- Telemetry counters were process-local in runtime path, with durability only via periodic persistence.

## Decision
- Add pluggable telemetry counter backend with safe default and explicit Redis shared mode:
  - `TELEMETRY_BACKEND=memory|redis`
  - `TELEMETRY_REDIS_URL` (or `REDIS_URL`) for Redis mode.
- Keep failure mode safe: if Redis is unavailable/misconfigured, fallback to in-memory backend.
- Enforce corporate write contract in gateway input validation:
  - `brain_store(domain="corporate")` requires non-empty `owner` and `match_key`.
- Add policy-first regression tests for update semantics:
  - corporate -> `append_version`,
  - build -> `upsert` (in-place mutable).

## Changes
- Runtime:
  - `unified/src/telemetry_counters.py` (new)
  - `unified/src/telemetry.py`
  - `unified/mcp-gateway/src/request_builders.py`
  - `unified/mcp-gateway/src/main.py`
- Tests:
  - `unified/tests/test_telemetry_counters.py` (new)
  - `unified/tests/test_policy_enforcement.py`
  - `unified/mcp-gateway/tests/test_request_builders.py`
  - `unified/mcp-gateway/tests/test_api_paths.py`
- Docs:
  - `docs/governance-layer.md`
  - `docs/operating-manual.md`

## Validation
- Local:
  - `pytest`: telemetry + policy + gateway targeted suites passed
  - `ruff`: changed runtime/tests passed
- CI:
  - Unified Smoke checks for latest commits passed (contract-integrity, smoke, guardrails, gateway-smoke, transport-parity).
  - External provider check `GitGuardian Security Checks` remains independently failing and outside repository-side code execution path.

## Risk
- Redis backend currently covers counters only; gauges/histograms remain per-process (documented).
- Redis calls are synchronous and should be used with local/low-latency Redis for best behavior.

## Status
- `fixed` — backlog #1, #2, #3 in governance layer are now closed in code and tests.
- `deferred (external)` — `GitGuardian Security Checks` requires provider-side triage/config, not local code patching.
