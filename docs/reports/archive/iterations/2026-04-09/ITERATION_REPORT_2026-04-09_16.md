# Iteration Report — 2026-04-09 (16)

- stream: obsidian integration / disabled-path contract
- status: fixed

## Problem

Obsidian contract guardrail validated feature-flag gating and capabilities structure, but did not assert stability of user-facing disabled-path reason semantics.

## Evidence

- `check_obsidian_contract.py` did not check the textual contract for disabled reasons in HTTP and local gateway paths.
- Disabled reasons are operationally important for support/debug workflows and should remain explicit.

## Decision

- Extended Obsidian guardrail with disabled-reason snippet checks:
  - gateway must keep explicit local-only/trusted-gateway guidance
  - HTTP transport must keep explicit `ENABLE_HTTP_OBSIDIAN_TOOLS=1` guidance
- Added regression test covering missing-snippet failures.

## Risk

- Low: static guardrail/test-only change.
- Positive: protects support-facing error semantics from accidental erosion.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_obsidian_contract_guardrail.py`
- `python3 scripts/check_obsidian_contract.py`
- `make pr-readiness`

## Files

- `scripts/check_obsidian_contract.py`
- `unified/tests/test_obsidian_contract_guardrail.py`
- `docs/archive/iterations/2026-04-09/ITERATION_REPORT_2026-04-09_16.md`
