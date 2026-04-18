# Iteration Report 31 (2026-04-08)

## Stream
Observability i health truthfulness (CI contract enforcement hardening)

## Problem
Nowy kontrakt `capabilities_response_contract` był chroniony testami lokalnymi, ale nie był częścią dedykowanych jobów `contract-integrity` we wszystkich workflowach CI.

## Evidence
- Workflowy uruchamiały tylko:
  - `unified/tests/test_contract_integrity.py`
  - `test_gateway_contract_integrity.py`
- Brak uruchamiania:
  - `unified/tests/test_capabilities_response_contract.py`
  - `test_capabilities_response_contract.py` (gateway)

## Decision
- Rozszerzono `contract-integrity` jobs w:
  - `.github/workflows/ci.yml`
  - `.github/workflows/ci-enhanced.yml`
  - `.github/workflows/unified-smoke.yml`
- Dodano uruchamianie nowych testów kontraktu odpowiedzi capabilities zarówno dla unified, jak i gateway.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_contract_integrity.py unified/tests/test_capabilities_response_contract.py` -> **7 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest discover -s tests -p "test_gateway_contract_integrity.py" -v` -> **3 tests OK**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest discover -s tests -p "test_capabilities_response_contract.py" -v` -> **1 test OK**

## Risk
- Bardzo niski: workflow/test hardening, brak zmian runtime.

## Status
**fixed**
