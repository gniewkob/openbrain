# Iteration Report 13 (2026-04-08)

## Stream
Gateway/API contract consistency

## Problem
W gatewayach nadal istniała duplikacja:
- limitów runtime (`MAX_SEARCH_TOP_K`, `MAX_LIST_LIMIT`, `MAX_SYNC_LIMIT`, `bulk max`)
- normalizacji odpowiedzi `/find` (`record` vs `memory` oraz flattening listy)

To zwiększało ryzyko dryfu kontraktowego.

## Evidence
- Limity były ustawiane ręcznie w kodzie gatewayów.
- Mapowanie odpowiedzi `/find` było inline, osobno per transport.

## Decision
- Wprowadzono wspólny kontrakt limitów:
  - `unified/contracts/runtime_limits.json`
- Dodano małe loadery limitów:
  - `unified/src/runtime_limits.py`
  - `unified/mcp-gateway/src/runtime_limits.py`
- Przepięto limity:
  - `unified/src/mcp_transport.py` (`max_bulk_items`)
  - `unified/mcp-gateway/src/main.py` (`MAX_*`)
- Dodano małe moduły normalizatorów odpowiedzi:
  - `unified/src/response_normalizers.py`
  - `unified/mcp-gateway/src/response_normalizers.py`
- Przepięto `brain_list`/`brain_search` na normalizatory w obu gatewayach.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_runtime_limits.py unified/tests/test_response_normalizers.py unified/tests/test_request_builders.py unified/tests/test_mcp_transport.py unified/tests/test_contract_parity.py` -> **49 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_runtime_and_normalizers tests.test_request_builders tests.test_api_paths tests.test_capabilities_manifest tests.test_obsidian_tools` -> **30 passed**

## Risk
- Niski: refaktoryzacja kontraktowa, semantyka endpointów i odpowiedzi narzędzi została zachowana.

## Status
**fixed**

