# Iteration Report 06 (2026-04-08)

## Stream
Gateway/API contract consistency

## Problem
`unified/src/mcp_transport.py` używał mieszanki endpointów legacy (`/api/memories/*`, `/api/admin/*`) i V1 (`/api/v1/memory/*`), co groziło rozjazdem kontraktu runtime względem aktualnej aplikacji FastAPI (`/api/v1`).

## Evidence
- Kod transportu wskazywał na ścieżki legacy dla `brain_update`, `brain_list`, `brain_delete`, `brain_export`, `brain_sync_check`, `brain_upsert_bulk`, `brain_maintain`.
- `unified/src/main.py` wystawia routery wyłącznie pod `prefix="/api/v1"`.

## Decision
- Ujednolicono transport MCP do V1:
  - `brain_update` -> `PATCH /api/v1/memory/{id}`
  - `brain_list` -> `POST /api/v1/memory/find` (z filtrem i sortowaniem po `updated_at_desc`)
  - `brain_delete` -> `DELETE /api/v1/memory/{id}`
  - `brain_export` -> `POST /api/v1/memory/export`
  - `brain_sync_check` -> `POST /api/v1/memory/sync-check`
  - `brain_upsert_bulk` -> `POST /api/v1/memory/bulk-upsert`
  - `brain_maintain` -> `POST /api/v1/memory/maintain`
- Dla `brain_list` dodano flattening wyników `/find` do listy rekordów pamięci (bez score), żeby zachować semantykę browse/list.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_mcp_transport.py` -> **15 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_contract_parity.py` -> **24 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_patch_endpoint.py unified/tests/test_access_control.py` -> **8 passed**

## Risk
- `brain_list` jest teraz mapowane na `/find`; jeżeli downstream oczekuje specyficznego zachowania starego `GET /api/memories` (np. innej paginacji), może zobaczyć różnice na krawędziach.

## Status
**fixed**

