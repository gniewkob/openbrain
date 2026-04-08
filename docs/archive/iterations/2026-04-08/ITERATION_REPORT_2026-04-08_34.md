# Iteration Report 34 (2026-04-08)

## Stream
Gateway/API contract consistency (capabilities metadata deduplication)

## Problem
`api_version` i `schema_changelog` w `brain_capabilities` były zduplikowane inline w obu transportach, co zwiększało ryzyko driftu treści przy kolejnych zmianach.

## Evidence
- Te same wartości metadanych capabilities utrzymywane ręcznie w:
  - `unified/src/mcp_transport.py`
  - `unified/mcp-gateway/src/main.py`

## Decision
- Dodano wspólny kontrakt:
  - `unified/contracts/capabilities_metadata.json`
- Dodano adaptery loadera:
  - `unified/src/capabilities_metadata.py`
  - `unified/mcp-gateway/src/capabilities_metadata.py`
- Oba transporty (`mcp_transport`, `gateway main`) korzystają teraz z `_CAP_META`.
- Rozszerzono testy integralności/kontraktu o weryfikację metadanych z kontraktu.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_contract_integrity.py unified/tests/test_capabilities_response_contract.py unified/tests/test_mcp_transport.py` -> **28 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest discover -s tests -p "test_gateway_contract_integrity.py" -v` -> **3 tests OK**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest discover -s tests -p "test_capabilities_response_contract.py" -v` -> **1 test OK**

## Risk
- Bardzo niski: refaktor kontraktowy, brak zmiany runtime behavior poza źródłem danych metadanych.

## Status
**fixed**
