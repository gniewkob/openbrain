# Iteration Report 16 (2026-04-08)

## Stream
Gateway/API contract consistency

## Problem
Brakowało jednego, szybkiego testu integralności, który weryfikuje wszystkie kontrakty (`capabilities`, `requests`, `limits`, `errors`, `paths`) razem z adapterami. Drift był wykrywany dopiero przez kilka oddzielnych testów.

## Evidence
- Kontrakty były już wydzielone do plików JSON i adapterów, ale bez jednej warstwy kontrolnej.
- Ewentualny błąd „wpięcia” kontraktu mógł przejść niezauważony w pojedynczych scenariuszach.

## Decision
- Dodano test integralności po stronie `unified`:
  - `unified/tests/test_contract_integrity.py`
- Dodano test integralności po stronie `mcp-gateway`:
  - `unified/mcp-gateway/tests/test_contract_integrity.py`
- Testy sprawdzają:
  - poprawność JSON kontraktów,
  - zgodność adapterów i stałych z kontraktami,
  - spójność helperów path mappingu.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_contract_integrity.py unified/tests/test_memory_paths.py unified/tests/test_http_error_adapter.py unified/tests/test_runtime_limits.py unified/tests/test_response_normalizers.py unified/tests/test_request_builders.py unified/tests/test_mcp_transport.py unified/tests/test_contract_parity.py` -> **59 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_contract_integrity tests.test_memory_paths tests.test_error_handling tests.test_runtime_and_normalizers tests.test_request_builders tests.test_api_paths tests.test_capabilities_manifest tests.test_obsidian_tools` -> **44 passed**

## Risk
- Bardzo niski: zmiana testowa, bez wpływu na runtime.

## Status
**fixed**

