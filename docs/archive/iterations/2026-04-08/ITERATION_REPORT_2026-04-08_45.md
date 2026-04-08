# Iteration Report 45 (2026-04-08)

## Problem

There was no single local command that combined static guardrails with fast
policy/contract smoke tests before creating a PR.

## Evidence

- Developers had to run multiple commands manually.
- Initial `check_pr_readiness.py` draft failed outside virtualenv due to missing
  pytest in system Python context.

## Decision

- Added `scripts/check_pr_readiness.py`:
  - runs `check_local_guardrails.py`,
  - runs guardrail-runner pytest suite,
  - runs contract integrity smoke pytest suite.
- Made runner robust by auto-selecting `/.venv/bin/python` for pytest steps.
- Added unit tests:
  - `unified/tests/test_pr_readiness_runner.py`
- Added `make pr-readiness` target.

## Validation

- `python3 scripts/check_pr_readiness.py` -> pass.
- `make pr-readiness` -> pass.
- `pytest -q unified/tests/test_pr_readiness_runner.py unified/tests/test_local_guardrails_runner.py unified/tests/test_contract_integrity.py unified/tests/test_capabilities_response_contract.py` -> pass.

## Risk

- Low: wrapper-level orchestration only; underlying policy checks unchanged.

## Status

`fixed`

