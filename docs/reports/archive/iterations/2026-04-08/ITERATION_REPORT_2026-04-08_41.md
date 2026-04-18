# Iteration Report 41 (2026-04-08)

## Problem

Governance/audit semantics (`created_by`, `updated_by`, actor override) were partially
covered by endpoint tests, but lacked a dedicated policy guardrail in CI guardrails.

## Evidence

- PATCH override behavior existed in code/tests, but regressions in schema or write path
  could bypass intended audit semantics without an explicit policy check.
- Guardrails job did not verify audit invariants.

## Decision

- Added `scripts/check_audit_semantics.py` to enforce:
  - `MemoryWriteRecord` does not accept `created_by`/`updated_by` from request payload,
  - API PATCH keeps authenticated actor override for `updated_by`,
  - write path keeps actor-bound audit assignments in `memory_writes.py`.
- Added unit regression: `unified/tests/test_audit_semantics_guardrail.py`.
- Wired policy script into `Unified Smoke Tests / guardrails`.

## Validation

- `python3 scripts/check_audit_semantics.py` -> pass.
- `pytest -q unified/tests/test_audit_semantics_guardrail.py unified/tests/test_patch_endpoint.py unified/tests/test_contract_integrity.py` -> pass.
- `python3 scripts/check_capabilities_truthfulness.py` -> pass.
- `python3 scripts/check_repo_hygiene.py` -> pass.

## Risk

- Low: guardrail is static and strict; if audit model changes intentionally, the script
  must be updated in the same PR.

## Status

`fixed`

