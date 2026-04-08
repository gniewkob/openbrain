# Iteration Report 11 (2026-04-08)

## Stream
Gateway/API contract consistency

## Problem
Payloady dla `brain_list` i `brain_update` były budowane inline w dwóch gatewayach. To zwiększało ryzyko driftu (np. różnice w `sort` dla `/find`, różne traktowanie `updated_by`).

## Evidence
- Dublowanie logiki filtrów i payloadu `/api/v1/memory/find`.
- Różne punkty normalizacji `updated_by` pomiędzy transportami.

## Decision
- Dodano wspólny kontrakt requestów:
  - `unified/contracts/request_contracts.json`
- Dodano małe moduły builderów requestów:
  - `unified/src/request_builders.py`
  - `unified/mcp-gateway/src/request_builders.py`
- Przepięto oba gatewaye:
  - `brain_list` korzysta z `build_list_filters()` + `build_find_list_payload()`
  - `brain_update` korzysta z `normalize_updated_by()`
- Utrzymano małe pliki i wąskie odpowiedzialności (bez dokładania logiki do `main.py`).

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_request_builders.py unified/tests/test_mcp_transport.py unified/tests/test_gateway_capabilities_parity.py unified/tests/test_contract_parity.py` -> **46 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_request_builders tests.test_api_paths tests.test_capabilities_manifest tests.test_obsidian_tools` -> **25 passed**

## Risk
- Niski: zmiana refaktoryzacyjna kontraktu requestów; brak zmian domenowej semantyki write/read.

## Status
**fixed**

