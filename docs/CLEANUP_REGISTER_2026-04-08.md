# Cleanup Register (2026-04-08)

Purpose: track artifacts that should be removed, consolidated, or reclassified
before final merge to keep repository hygiene.

## Candidates

| Path | Type | Proposed action | Reason | Timing |
|---|---|---|---|---|
| `reproduce_hang.py` | Local debug artifact | ✅ Removed | Ad-hoc troubleshooting helper; not part of product/runtime contract | Done (2026-04-08) |
| `docs/ITERATION_REPORT_2026-04-08_*.md` | Iteration logs | ✅ Archived under `docs/archive/iterations/2026-04-08/` + indexed | High audit value while iterating, high noise as permanent long-term docs | Done (2026-04-08) |
| `docs/COMPLETION_PLAN_5_5.md`, `docs/QUICK_START_5_5.md`, `docs/ROADMAP_VISUAL_5_5.md` | Plan artifacts | ✅ Archived under `docs/archive/legacy/2026-04-07/` | Potential duplication vs `docs/operating-manual.md` and `docs/architecture.md`; kept for history only | Done (2026-04-08) |
| `docs/AUDIT_GAP_ANALYSIS_360_2026-04-07.md`, `docs/audit-report-360-2026-04-07.md` | Audit docs | ✅ Archived under `docs/archive/legacy/2026-04-07/` | Reduce doc sprawl and conflicting sources of truth in top-level `docs/` | Done (2026-04-08) |

## Keep (not cleanup candidates)

These are new governance/contract assets and should stay:

- `unified/contracts/*`
- `unified/src/{capabilities_manifest.py,capabilities_health.py,request_builders.py,runtime_limits.py,http_error_adapter.py,response_normalizers.py,memory_paths.py}`
- `unified/mcp-gateway/src/{capabilities_manifest.py,capabilities_health.py,request_builders.py,runtime_limits.py,http_error_adapter.py,response_normalizers.py,memory_paths.py}`
- `scripts/check_release_gate.py`
- `scripts/check_repo_hygiene.py`
- `scripts/check_capabilities_truthfulness.py`
- `scripts/check_audit_semantics.py`
- `scripts/check_obsidian_contract.py`
- `scripts/check_local_guardrails.py`
- `scripts/check_pr_readiness.py`
- Contract/integrity/parity tests added in `unified/tests` and `unified/mcp-gateway/tests`

## Exit criteria for cleanup

1. No ad-hoc local debug scripts left in repo root.
2. One canonical architecture doc and one canonical operating manual path.
3. Iteration reports either:
   - collapsed into a single final synthesis report, or
   - moved to an archive location with explicit index.
4. All remaining new files are referenced by CI, runtime, or authoritative docs.
