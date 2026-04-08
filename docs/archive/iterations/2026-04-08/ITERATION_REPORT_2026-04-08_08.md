# Iteration Report 08 (2026-04-08)

## Stream
Gateway/API contract consistency

## Problem
W repo są dwa gatewaye MCP (`unified/src/mcp_transport.py` oraz `unified/mcp-gateway/src/main.py`) z dublowanymi listami narzędzi (`CORE_TOOLS`, `ADVANCED_TOOLS`, `ADMIN_TOOLS`). Bez strażnika testowego istnieje wysokie ryzyko cichego driftu capabilities.

## Evidence
- Definicje list narzędzi są utrzymywane niezależnie w dwóch plikach.
- Wcześniejsze zmiany wykazały realne rozjazdy endpointów i kontraktów.

## Decision
- Dodano test parity:
  - `unified/tests/test_gateway_capabilities_parity.py`
- Test parsuje stałe listy narzędzi z `unified/mcp-gateway/src/main.py` i porównuje je 1:1 z `unified/src/mcp_transport.py`.
- Wybrano parsing AST zamiast importu modułu gatewaya, żeby uniknąć konfliktów importu `src.*` i zależności runtime.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_gateway_capabilities_parity.py` -> **1 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_mcp_transport.py unified/tests/test_gateway_capabilities_parity.py` -> **18 passed**

## Risk
- Niski: test nie zmienia runtime; zwiększa tylko wykrywalność regresji.

## Status
**fixed**

