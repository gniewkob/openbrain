# Iteration Report — 2026-04-09 (14)

- stream: governance / actor normalization parity
- status: fixed

## Problem

Actor normalization and legacy-hit response normalization are implemented in both HTTP transport and stdio gateway, but there was no dedicated parity guardrail on `response_normalizers`.

## Evidence

- `unified/src/response_normalizers.py` and `unified/mcp-gateway/src/response_normalizers.py` are parallel modules.
- Existing audit guardrail covers API/write-path actor enforcement, but not response normalizer parity drift.

## Decision

- Added static parity guardrail:
  - `scripts/check_response_normalizers_parity.py`
- Wired guardrail into:
  - `scripts/check_local_guardrails.py`
  - `scripts/check_pr_readiness.py` guardrail-runner tests
- Added dedicated tests and updated runner assertions/docs.

## Risk

- Low: static checks only.
- Positive: protects cross-transport consistency for `created_by/updated_by` normalization semantics in read/search outputs.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_response_normalizers_parity_guardrail.py unified/tests/test_local_guardrails_runner.py`
- `python3 scripts/check_response_normalizers_parity.py`
- `make pr-readiness`

## Files

- `scripts/check_response_normalizers_parity.py`
- `scripts/check_local_guardrails.py`
- `scripts/check_pr_readiness.py`
- `unified/tests/test_response_normalizers_parity_guardrail.py`
- `unified/tests/test_local_guardrails_runner.py`
- `docs/operating-manual.md`
