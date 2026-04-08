# Iteration Report 10 (2026-04-08)

## Stream
Gateway/API contract consistency

## Problem
Dwa gatewaye (`unified/src/mcp_transport.py` i `unified/mcp-gateway/src/main.py`) utrzymywały listy narzędzi capabilities w kodzie niezależnie. To podnosiło ryzyko driftu i niespójnych deklaracji platformy.

## Evidence
- Duplikacja list: core/advanced/admin oraz lokalnych narzędzi Obsidian.
- Wcześniejsze iteracje już wykryły realne rozjazdy kontraktowe pomiędzy warstwami.

## Decision
- Wprowadzono pojedyncze źródło prawdy:
  - `unified/contracts/capabilities_manifest.json`
- Dodano małe loadery manifestu:
  - `unified/src/capabilities_manifest.py`
  - `unified/mcp-gateway/src/capabilities_manifest.py`
- Oba gatewaye ładują teraz listy toolsów z tego samego manifestu.
- Dodano/zmieniono testy:
  - `unified/tests/test_gateway_capabilities_parity.py`
  - `unified/mcp-gateway/tests/test_capabilities_manifest.py`

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_mcp_transport.py unified/tests/test_gateway_capabilities_parity.py unified/tests/test_contract_parity.py` -> **43 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_capabilities_manifest tests.test_obsidian_tools` -> **16 passed**

## Risk
- Niski: zmiana architektonicznie porządkująca, bez zmiany semantyki runtime narzędzi.

## Status
**fixed**

