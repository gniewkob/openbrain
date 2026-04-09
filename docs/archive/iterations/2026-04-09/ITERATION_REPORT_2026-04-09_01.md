# Iteration Report — 2026-04-09 (01)

- stream: observability / telemetry fallback visibility
- status: fixed

## Problem

Telemetry counter backend supports fallback (`redis -> memory`), but runtime did not expose an explicit metric signal when fallback was activated.

## Evidence

- `unified/src/telemetry_counters.py` returned in-memory backend on Redis misconfiguration/runtime failure without structured fallback metadata.
- `unified/src/telemetry.py` initialized counters without incrementing a dedicated fallback indicator.
- Existing tests covered fallback behavior, but not fallback visibility semantics.

## Decision

- Added structured backend build metadata in telemetry counters (`CounterBackendBuildMeta` and `build_counter_backend_with_meta`).
- Preserved existing API (`build_counter_backend`) for compatibility.
- Added runtime observability signal:
  - new counter `telemetry_counter_backend_fallback_total`,
  - incremented on TelemetryRegistry init when fallback reason is present.
- Added regression coverage for:
  - backend build metadata semantics,
  - fallback counter increment on Redis fallback,
  - no increment when fallback is not active.

## Risk

- Low: no API contract break; legacy helper retained.
- Medium operational note: fallback counter increments on registry initialization, so process restarts contribute to total value (acceptable for alerting intent).

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_telemetry_counters.py unified/tests/test_metrics.py` → pass
- `make pr-readiness` → pass

## Files

- `unified/src/telemetry_counters.py`
- `unified/src/telemetry.py`
- `unified/tests/test_telemetry_counters.py`
- `unified/tests/test_metrics.py`
