# Iteration Report 07 (2026-04-08)

## Stream
Governance i audit semantics

## Problem
W transporcie MCP (`unified/src/mcp_transport.py`) `brain_update` wysyłał `updated_by` na stałe jako `"agent"`, bez możliwości jawnego przekazania aktora aktualizacji.

## Evidence
- Sygnatura `brain_update` nie miała argumentu `updated_by`.
- Payload PATCH zawsze zawierał `"updated_by": "agent"`.
- To ograniczało wiarygodność śladu auditowego przy wywołaniach narzędziowych.

## Decision
- Dodano jawny parametr `updated_by: str = "agent"` do `brain_update`.
- Payload PATCH używa teraz przekazanego aktora.
- Dodano bezpieczny fallback: pusty/whitespace `updated_by` jest normalizowany do `"agent"`.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_mcp_transport.py` -> **17 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_contract_parity.py unified/tests/test_patch_endpoint.py` -> **29 passed**

## Risk
- Niski: zmiana rozszerza kontrakt wejściowy i nie łamie kompatybilności wstecznej (domyślnie nadal `"agent"`).

## Status
**fixed**

