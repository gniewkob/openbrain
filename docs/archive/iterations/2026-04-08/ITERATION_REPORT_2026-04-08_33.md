# Iteration Report 33 (2026-04-08)

## Stream
Observability i health truthfulness (capabilities metadata parity)

## Problem
`brain_capabilities` miał już parity health/obsidian, ale metadane diagnostyczne (`api_version`, `schema_changelog`) były wcześniej tylko w stdio gateway.

## Evidence
- HTTP transport `brain_capabilities` nie zwracał `api_version` i `schema_changelog`.
- Klienci zależni od tych pól musieli traktować transporty nierównomiernie.

## Decision
- Dodano do HTTP transport `brain_capabilities`:
  - `api_version`
  - `schema_changelog`
- Rozszerzono kontrakt:
  - `unified/contracts/capabilities_response_contract.json`
  o wymagane top-level keys `api_version` i `schema_changelog`.
- Rozszerzono testy kontraktu odpowiedzi dla obu transportów.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_capabilities_response_contract.py unified/tests/test_mcp_transport.py` -> **21 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_capabilities_response_contract -v` -> **1 test OK**
- `./unified/.venv/bin/pytest -q unified/tests/test_contract_integrity.py` -> **6 passed**

## Risk
- Niski: addytywne pola diagnostyczne, bez zmiany semantyki write/search.

## Status
**fixed**
