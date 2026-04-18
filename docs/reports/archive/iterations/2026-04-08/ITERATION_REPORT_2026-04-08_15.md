# Iteration Report 15 (2026-04-08)

## Stream
Gateway/API contract consistency

## Problem
Ścieżki endpointów `memory` były utrzymywane jako string literals w wielu miejscach (`mcp_transport` i `mcp-gateway/main`), co utrudniało bezpieczne zmiany i zwiększało ryzyko driftu.

## Evidence
- Rozproszone odwołania do `"/api/v1/memory/*"` oraz względnych `"/find"`, `"/write"`, `"/sync-check"` itp.
- Brak wspólnego kontraktu mapowania ścieżek.

## Decision
- Wprowadzono wspólny kontrakt endpointów:
  - `unified/contracts/memory_paths.json`
- Dodano małe adaptery ścieżek:
  - `unified/src/memory_paths.py`
  - `unified/mcp-gateway/src/memory_paths.py`
- Przepięto oba gatewaye na helpery path mappingu:
  - `unified/src/mcp_transport.py`
  - `unified/mcp-gateway/src/main.py`
- Dodano testy kontraktu ścieżek:
  - `unified/tests/test_memory_paths.py`
  - `unified/mcp-gateway/tests/test_memory_paths.py`

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_memory_paths.py unified/tests/test_http_error_adapter.py unified/tests/test_runtime_limits.py unified/tests/test_response_normalizers.py unified/tests/test_request_builders.py unified/tests/test_mcp_transport.py unified/tests/test_contract_parity.py` -> **53 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_memory_paths tests.test_error_handling tests.test_runtime_and_normalizers tests.test_request_builders tests.test_api_paths tests.test_capabilities_manifest tests.test_obsidian_tools` -> **41 passed**

## Risk
- Niski: refaktoryzacja kontraktu ścieżek, bez zmiany semantyki API.

## Status
**fixed**

