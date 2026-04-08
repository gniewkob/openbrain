# Iteration Report 09 (2026-04-08)

## Stream
Obsidian integration

## Problem
W `brain_capabilities` (transport HTTP MCP) status Obsidian był binarny (`enabled|disabled`), ale bez jasnego `reason` w ścieżce disabled, co utrudniało operacyjne rozróżnienie „wyłączone konfiguracyjnie” vs „awaria”.

## Evidence
- `obsidian_http` zawierał tylko `status` i `tools`.
- Brak komunikatu diagnostycznego przy `status=disabled`.

## Decision
- Dodano pole `reason` do `obsidian_http` w `unified/src/mcp_transport.py`:
  - `None` gdy enabled,
  - kontrolowany komunikat diagnostyczny gdy disabled.
- Rozszerzono testy capabilities o asercję `reason`.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_mcp_transport.py unified/tests/test_gateway_capabilities_parity.py` -> **18 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_contract_parity.py` -> **24 passed**

## Risk
- Bardzo niski: zmiana addytywna w payloadzie diagnostycznym, bez wpływu na ścieżki CRUD.

## Status
**fixed**

