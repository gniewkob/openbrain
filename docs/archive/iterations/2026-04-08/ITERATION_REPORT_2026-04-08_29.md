# Iteration Report 29 (2026-04-08)

## Stream
Observability i health truthfulness (capabilities response contract guard)

## Problem
Mieliśmy poprawione payloady `brain_capabilities`, ale bez jawnego kontraktu odpowiedzi groził powrót driftu semantycznego (braki kluczy lub niespójne pola między transportami).

## Evidence
- Brak dedykowanego kontraktu JSON dla struktury odpowiedzi capabilities.
- Brak testu, który waliduje minimalny wymagany schemat w obu transportach.

## Decision
- Dodano nowy kontrakt:
  - `unified/contracts/capabilities_response_contract.json`
- Dodano testy walidujące kontrakt:
  - HTTP transport: `unified/tests/test_capabilities_response_contract.py`
  - stdio gateway: `unified/mcp-gateway/tests/test_capabilities_response_contract.py`
- Kontrakt obejmuje:
  - wymagane top-level keys,
  - wymagane pola `backend`,
  - wymagane pola `obsidian`,
  - dozwolone wartości `obsidian.mode` i `obsidian.status`.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_capabilities_response_contract.py unified/tests/test_mcp_transport.py unified/tests/test_transport_parity.py` -> **31 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_capabilities_response_contract tests.test_obsidian_tools -v` -> **16 passed**

## Risk
- Bardzo niski: zmiana kontraktowo-testowa, bez wpływu na runtime ścieżek write/search.

## Status
**fixed**
