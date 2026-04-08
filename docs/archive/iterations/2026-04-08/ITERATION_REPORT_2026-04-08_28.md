# Iteration Report 28 (2026-04-08)

## Stream
Obsidian integration (capabilities contract normalization)

## Problem
Klienci capability payload musieli rozgałęziać logikę między `obsidian_http` i `obsidian_local` zależnie od transportu. To zwiększało złożoność integracji i ryzyko niespójnych interpretacji.

## Evidence
- HTTP transport zwracał `obsidian_http`.
- Stdio gateway zwracał `obsidian_local`.
- Brak wspólnego klucza kontraktowego dla obu transportów.

## Decision
- Dodano wspólny, transport-agnostyczny klucz:
  - `obsidian = { mode, status, tools, reason }`
- Zachowano kompatybilność wsteczną:
  - `obsidian_http` i `obsidian_local` pozostają bez usuwania.
- Rozszerzono testy:
  - `unified/tests/test_mcp_transport.py`
  - `unified/tests/test_transport_parity.py`
  - `unified/mcp-gateway/tests/test_obsidian_tools.py`

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_mcp_transport.py unified/tests/test_transport_parity.py` -> **30 passed**
- `cd unified/mcp-gateway && .venv/bin/python -m unittest tests.test_obsidian_tools -v` -> **15 passed**

## Risk
- Niski: zmiana addytywna w payloadzie capabilities; brak breaking changes dla istniejących klientów.

## Status
**fixed**
