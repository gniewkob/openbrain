# Iteration Report 12 (2026-04-08)

## Stream
Gateway/API contract consistency

## Problem
Mimo wcześniejszej refaktoryzacji, payloady `brain_search` i `brain_sync_check` nadal były składane inline w obu gatewayach. To pozostawiało ostatni punkt driftu kontraktowego.

## Evidence
- Dublowanie logiki payloadów w:
  - `unified/src/mcp_transport.py`
  - `unified/mcp-gateway/src/main.py`
- Brak wspólnego buildera dla `search` i `sync-check`.

## Decision
- Rozszerzono małe moduły builderów requestów o:
  - `build_find_search_payload()`
  - `build_sync_check_payload()`
- Przepięto oba gatewaye (`mcp_transport` i `mcp-gateway/main`) na te funkcje.
- Nie zmieniano semantyki endpointów ani walidacji biznesowej.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_request_builders.py unified/tests/test_mcp_transport.py unified/tests/test_contract_parity.py` -> **46 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_request_builders tests.test_api_paths tests.test_capabilities_manifest` -> **12 passed**

## Risk
- Niski: refaktoryzacja eliminująca duplikację; payloady pozostały zgodne z bieżącym kontraktem V1.

## Status
**fixed**

