# Iteration Report 27 (2026-04-08)

## Stream
Governance i audit semantics

## Problem
Kontrakt audytowy `updated_by` był poprawny logicznie (actor z auth), ale nie był wymuszony na granicy API. Payload mógł dalej nieść spoofed `updated_by`, co zwiększa ryzyko regresji przy przyszłych refaktorach warstwy write.

## Evidence
- Endpoint `PATCH /api/v1/memory/{id}` przekazywał `MemoryUpdate` dalej bez nadpisania `updated_by`.
- Testy potwierdzały actor z auth, ale nie sprawdzały twardo, że przekazany dalej `updated_by` jest już zsynchronizowany z podmiotem uwierzytelnionym.

## Decision
- W `v1_update` dodano boundary hardening:
  - `safe_data = data.model_copy(update={"updated_by": actor})`
  - dalej przekazywane jest `safe_data`.
- Rozszerzono testy endpointu:
  - `test_patch_overrides_payload_updated_by_with_authenticated_subject`
- Uzupełniono operating manual o jednoznaczny zapis kontraktu.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_patch_endpoint.py` -> **6 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_mcp_transport.py unified/tests/test_transport_parity.py` -> **30 passed**

## Risk
- Niski: zachowanie zgodne z dotychczasową intencją governance; zmiana redukuje powierzchnię spoofingu metadanych.

## Status
**fixed**
