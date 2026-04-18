# Iteration Report 24 (2026-04-08)

## Stream
Observability i health truthfulness (capabilities cross-transport parity)

## Problem
`brain_capabilities` w HTTP transport (`unified/src/mcp_transport.py`) nie zwracał sekcji `backend`, podczas gdy stdio gateway (`mcp-gateway/src/main.py`) raportował status oparty o probe `/readyz` i fallback `/healthz`.

## Evidence
- Rozjazd kontraktu capability payload między transportami:
  - stdio: posiadał `backend` (status/api/db/vector_store/probe/reason),
  - HTTP: brak `backend` (tylko tiery + obsidian flag).
- Ryzyko operacyjne: różne narzędzia klienckie dostawały różny obraz zdrowia platformy.

## Decision
- Dodano do HTTP transport:
  - `HEALTH_PROBE_TIMEOUT`
  - `_get_backend_status()` z semantyką:
    - preferuj `/readyz`,
    - fallback do `/healthz`,
    - rozróżnienie `ok` / `degraded` / `unavailable`.
- `brain_capabilities()` w HTTP transport teraz zwraca `backend` analogicznie do stdio gateway.
- Rozszerzono testy:
  - `unified/tests/test_mcp_transport.py` (probe semantics + capabilities backend key)
  - `unified/tests/test_transport_parity.py` (parity wspólnych pól capabilities).

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_mcp_transport.py` -> **20 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_transport_parity.py unified/tests/test_mcp_transport.py` -> **27 passed**

## Risk
- Niski: zmiana dotyczy diagnostycznego payloadu capabilities; brak wpływu na write/search contract.

## Status
**fixed**
