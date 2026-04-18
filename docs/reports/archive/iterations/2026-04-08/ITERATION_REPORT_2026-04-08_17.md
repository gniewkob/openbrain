# Iteration Report 17 (2026-04-08)

## Stream
Performance i cleanups (CI hardening)

## Problem
Testy kontraktowe działały lokalnie, ale nie były wymuszone jako osobna bramka CI. To pozwalało na potencjalny drift między kontraktami JSON i adapterami w gatewayach.

## Evidence
- Workflowy CI nie miały dedykowanego joba `contract-integrity`.
- Brak obowiązkowego uruchamiania testów:
  - `unified/tests/test_contract_integrity.py`
  - `unified/mcp-gateway/tests/test_gateway_contract_integrity.py`

## Decision
- Dodano dedykowane kroki CI:
  - `.github/workflows/ci.yml` -> job `contract-integrity`
  - `.github/workflows/ci-enhanced.yml` -> job `contract-integrity`
  - `.github/workflows/unified-smoke.yml` -> job `contract-integrity`
- Utrzymano lekką formę uruchamiania:
  - `pytest` dla unified
  - `unittest discover` dla mcp-gateway (uniknięcie konfliktu namespace testów)
- Zmieniono nazwę testu gatewayowego na unikalną:
  - `test_gateway_contract_integrity.py`

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_contract_integrity.py unified/tests/test_mcp_transport.py unified/tests/test_contract_parity.py` -> **47 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_gateway_contract_integrity tests.test_memory_paths tests.test_error_handling tests.test_runtime_and_normalizers tests.test_request_builders tests.test_api_paths tests.test_capabilities_manifest tests.test_obsidian_tools` -> **44 passed**

## Risk
- Niski: zmiany w workflowach i testach; brak wpływu na runtime.

## Status
**fixed**

