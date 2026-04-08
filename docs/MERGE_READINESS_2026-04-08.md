# Merge Readiness Snapshot (2026-04-08)

## Decision

Current branch state is **conditionally merge-ready** for the governance/contract
stream, provided the PR scope is intentionally limited to the implemented workstreams
 and validated with the checklist below.

## Scope covered

- Capabilities truthfulness and health semantics hardening (`health.overall`,
  `health.components`, probe fallback chain).
- Contract centralization and transport parity reinforcement.
- Governance/audit semantics hardening (`updated_by` authenticated-actor override).
- Obsidian feature-flag and capabilities contract guardrails.
- Local/CI guardrail orchestration:
  - `check_local_guardrails.py`
  - `check_pr_readiness.py`

## Mandatory pre-merge checks

Run from repo root:

```bash
python3 scripts/check_pr_readiness.py
python3 scripts/check_release_gate.py
```

Expected:
- `PR readiness bundle passed.`
- release gate reports branch protected and no missing checks.

Latest local verification (2026-04-08):
- `python3 scripts/check_pr_readiness.py` -> pass
- `python3 scripts/check_release_gate.py` -> pass (`master` protected, 9 required checks, no missing checks)

## Status summary

- **Done**
  - Release gate enforcement in CI (`RELEASE_GATE_ENFORCE=1`).
  - Guardrail scripts for hygiene, capabilities truthfulness, audit semantics,
    Obsidian contract.
  - Consolidated local runners + unit tests for runner behavior.
  - Iteration and cleanup traceability archived/indexed.
  - Governance backlog closure:
    - shared telemetry counter backend (`memory`/`redis` with fallback),
    - gateway corporate store contract hardening (`owner` + `match_key`),
    - explicit domain-update policy tests (corporate versioning vs build in-place).
  - Obsidian adapter hardening:
    - vault discovery now falls back to configured env vault mappings when CLI is unavailable.
- **Deferred**
  - Controlled live Obsidian E2E execution in target environment (roundtrip test coverage exists, but runtime execution still needs explicit environment approval/variables).
  - Additional doc consolidation outside current governance stream.

## Current check posture (latest branch head)

- Internal CI checks: **pass** (`lint`, `test`, `security`, `contract-integrity`, and full `Unified Smoke Tests` set).
- External check: **pass** (`GitGuardian Security Checks`) after branch history rewrite removing flagged workflow literals from PR commit range.

## Risks before merge

- Large dirty tree increases accidental scope risk.
- Coexistence of two MCP transports still requires parity discipline.
- Live Obsidian behavior remains environment-dependent until controlled E2E is executed.

## Minimal PR boundary recommendation

- Include only files tied to:
  - contracts/adapters/parity tests,
  - guardrail scripts and workflow wiring,
  - governance endpoint semantics,
  - supporting docs (`operating-manual`, `architecture`, iteration index/synthesis, cleanup register).
- Exclude unrelated opportunistic refactors from the same branch snapshot.

## Rollback plan

- Revert guardrail/workflow additions first if CI gating blocks unrelated delivery:
  - `.github/workflows/unified-smoke.yml`
  - `scripts/check_*.py` introduced in this stream
- Keep contract and endpoint fixes intact where possible.
