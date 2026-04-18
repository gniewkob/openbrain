# Final Merge Packet (2026-04-08)

## Decision

Branch `codex/governance-guardrails-readiness` is **merge-ready** for the
governance/contract stream.

## Why this is merge-ready

- PR checks are green (`gh pr checks 1`): CI suites and `GitGuardian Security Checks`.
- Governance backlog criticals closed in code/tests:
  - capabilities/health truthfulness,
  - gateway corporate store invariants (`owner`, `match_key`),
  - domain update policy tests,
  - telemetry shared counters backend.
- Obsidian stream hardened and validated:
  - env/runtime resilience,
  - controlled live E2E roundtrip executed successfully on isolated vault mapping.

## Scope delivered

- Contracts/adapters/parity/guardrails across unified + gateway transport.
- CI hardening (secret-scan hygiene + concurrency cancellation).
- Obsidian integration hardening (parser/runtime/test execution path).
- Governance documentation synchronized with implementation state.

## Impact

- Better operational truthfulness and lower false outage/false health signals.
- Lower CI noise and fewer duplicate runs.
- Reduced risk of secret-scan blockers from workflow literals.
- Safer, testable Obsidian path in controlled environments.

## Controls

- Local gate:
  - `python3 scripts/check_pr_readiness.py`
  - `python3 scripts/check_release_gate.py`
- CI gate:
  - required checks on branch protection.
- Runtime gate:
  - controlled Obsidian E2E remains opt-in and isolated by mapping.

## Rollback

- If merge causes CI gating friction, rollback order:
  1. workflow-only changes (`.github/workflows/*`),
  2. docs-only updates,
  3. keep core contract/governance fixes unless regression is proven.

## Post-merge next actions

1. Normalize runtime profile for container-reachable Obsidian mappings across environments.
2. Continue doc consolidation outside governance-critical artifacts.
3. Start next backlog stream focused on transport modernization (`mcp_transport.py`) with parity guardrails retained.
