# Iteration Report 44 (2026-04-08)

## Problem

The guardrails job executed policy scripts, but did not validate the new runner
or script-loading test harnesses themselves in CI.

## Evidence

- New runner (`check_local_guardrails.py`) and script-based unit tests existed.
- CI could still miss regressions in runner orchestration flow without explicit test step.

## Decision

- Updated `Unified Smoke Tests / guardrails`:
  - install `pytest`,
  - run guardrail-focused unit tests:
    - `unified/tests/test_local_guardrails_runner.py`
    - `unified/tests/test_audit_semantics_guardrail.py`
    - `unified/tests/test_obsidian_contract_guardrail.py`

## Validation

- `pytest -q unified/tests/test_local_guardrails_runner.py unified/tests/test_audit_semantics_guardrail.py unified/tests/test_obsidian_contract_guardrail.py` -> pass.

## Risk

- Low: slight guardrails job runtime increase due to additional lightweight tests.

## Status

`fixed`

