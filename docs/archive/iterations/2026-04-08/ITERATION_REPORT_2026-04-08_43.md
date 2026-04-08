# Iteration Report 43 (2026-04-08)

## Problem

Guardrails checks were increasingly spread across multiple independent CI steps,
which made local pre-push validation verbose and easier to run inconsistently.

## Evidence

- We had separate static policy scripts for hygiene, capabilities truthfulness,
  audit semantics, and Obsidian contract.
- Running all checks manually required multiple commands in fixed order.

## Decision

- Added consolidated static guardrail runner:
  - `scripts/check_local_guardrails.py`
- Runner executes deterministic sequence:
  - `check_repo_hygiene.py`
  - `check_capabilities_truthfulness.py`
  - `check_audit_semantics.py`
  - `check_obsidian_contract.py`
- Updated `Unified Smoke Tests / guardrails` to use the consolidated runner.
- Added unit regression coverage for runner flow and fail-fast behavior:
  - `unified/tests/test_local_guardrails_runner.py`

## Validation

- `python3 scripts/check_local_guardrails.py` -> pass.
- `pytest -q unified/tests/test_local_guardrails_runner.py unified/tests/test_audit_semantics_guardrail.py unified/tests/test_obsidian_contract_guardrail.py` -> pass.
- Individual scripts remain green when run directly.

## Risk

- Low: wrapper script introduces orchestration layer; mitigated by direct tests and
  keeping underlying scripts unchanged.

## Status

`fixed`

