# Iteration Report 14 (2026-04-08)

## Stream
Gateway/API contract consistency

## Problem
Semantyka błędów HTTP była niespójnie zakodowana inline, a część normalizacji odpowiedzi i limitów runtime była nadal rozproszona.

## Evidence
- `_raise` w stdio gateway i `_safe_req` w HTTP transport implementowały zasady błędów osobno.
- Limity i normalizacje `/find` były utrzymywane w wielu miejscach.

## Decision
- Dodano wspólny kontrakt błędów:
  - `unified/contracts/http_error_contracts.json`
- Dodano małe adaptery błędów:
  - `unified/src/http_error_adapter.py`
  - `unified/mcp-gateway/src/http_error_adapter.py`
- Przepięto:
  - `unified/src/mcp_transport.py` (`_safe_req`)
  - `unified/mcp-gateway/src/main.py` (`_raise`)
- Dodano kontrakt limitów:
  - `unified/contracts/runtime_limits.json`
- Dodano loadery i normalizatory odpowiedzi:
  - `unified/src/runtime_limits.py`
  - `unified/mcp-gateway/src/runtime_limits.py`
  - `unified/src/response_normalizers.py`
  - `unified/mcp-gateway/src/response_normalizers.py`
- Ustabilizowano test `mcp-gateway/tests/test_error_handling.py` przez `load_gateway_main()` (bez konfliktu namespace `src/common`).

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_http_error_adapter.py unified/tests/test_runtime_limits.py unified/tests/test_response_normalizers.py unified/tests/test_request_builders.py unified/tests/test_mcp_transport.py unified/tests/test_contract_parity.py` -> **51 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_error_handling tests.test_runtime_and_normalizers tests.test_request_builders tests.test_api_paths tests.test_capabilities_manifest tests.test_obsidian_tools` -> **39 passed**

## Risk
- Niski: zmiany kontraktowo-refaktoryzacyjne bez zmiany semantyki domenowej.

## Status
**fixed**

