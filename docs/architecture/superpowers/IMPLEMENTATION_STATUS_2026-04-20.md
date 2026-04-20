# Superpowers Plans/Specs — Implementation Status (2026-04-20)

## Purpose
This note classifies `docs/architecture/superpowers/{plans,specs}` into:
- keep as active reference,
- keep as historical context,
- optional archive candidate.

It is based on current `master` state (`c915149`) and green CI workflows.

## Summary
- Operational backlog in GitHub: no open PRs, no open issues.
- Most April plans/specs are implemented and now historical.
- The only still-relevant engineering follow-up from these artifacts is optional further decomposition of `detect_changes()` and environment stabilization for integration tests.

## Decisions
| File | State vs codebase | Decision | Why |
|---|---|---|---|
| `plans/2026-04-05-track-a-p0-hardening.md` | Implemented | Keep historical | Secret scanning, parity checks, error envelope behavior, and readiness probing are present in runtime/tests. |
| `plans/2026-04-05-track-b-p1-fixes.md` | Implemented | Keep historical | Gateway bounds validation and related tests are present. |
| `plans/2026-04-06-audit-remediation-p1-p2.md` | Implemented (operationally) | Keep historical | Main remediation outcomes are reflected in current code and CI posture. |
| `plans/2026-04-06-m2-write-truncation-warning.md` | Implemented | Keep historical | `_warn_if_truncated()` and warning propagation tests exist. |
| `plans/2026-04-11-phase0-merge-gate.md` | Obsolete (one-time git operation) | Archive candidate | Branch merge gate steps are completed and no longer reusable as active runbook. |
| `plans/2026-04-11-phase1-refactoring.md` | Partially implemented | Keep active reference | `run_maintenance()` decomposition is done; `detect_changes()` further decomposition remains optional. |
| `plans/2026-04-11-phase2-mcp-transport.md` | Decision implemented | Keep active reference | Transport ADR accepted and parity guardrails are active; useful for future transport changes. |
| `plans/2026-04-11-phase3-quality.md` | Largely superseded | Keep historical | Targets from that phase are below current quality bar and CI already enforces stronger gates. |
| `plans/2026-04-18-production-readiness-hardening.md` | Implemented with follow-up items | Keep active reference | Useful as a production-hardening ledger and checklist baseline. |
| `specs/2026-04-05-track-a-p0-hardening-design.md` | Implemented design | Keep historical | Captures rationale and scope for security hardening decisions. |
| `specs/2026-04-05-track-b-p1-fixes-design.md` | Implemented design | Keep historical | Captures rationale for validation and test hardening. |
| `specs/2026-04-11-closure-plan-design.md` | Partially stale checklist | Keep historical | Valuable as context, but task checkboxes are not the source of truth now. |
| `specs/ADR-001-mcp-transport-architecture.md` | Active architecture decision | Keep active reference | ADR remains valid and should stay discoverable. |

## Evidence Snapshot
- Secret scan middleware: `unified/src/middleware.py`
- Gateway bounds validation: `unified/mcp-gateway/src/main.py`, `unified/tests/test_gateway_validation.py`
- Truncation warning path: `unified/src/memory_writes.py`, `unified/tests/test_memory_writes.py`
- CI hard gates (mypy, format, coverage fail-under): `.github/workflows/ci.yml`, `.github/workflows/ci-enhanced.yml`
- Runtime readiness and Docker healthcheck: `unified/src/api/v1/health.py`, `docker-compose.unified.yml`

## Recommended Next Step
If you want a cleaner tree, move only `plans/2026-04-11-phase0-merge-gate.md` to a dated archive folder first; keep all other files in place with this status ledger as the canonical index.
