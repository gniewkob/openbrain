# Iteration Report — 2026-04-09 (02)

- stream: observability / monitoring contract
- status: fixed

## Problem

Telemetry backend fallback visibility was implemented in code, but not fully propagated into monitoring contract and Prometheus alerting.

## Evidence

- Counter `telemetry_counter_backend_fallback_total` existed in runtime telemetry.
- Monitoring contract (`openbrain-metrics-contract.json`) did not include that counter.
- Prometheus rules had no explicit recording rule or alert for fallback events.

## Decision

- Extended monitoring contract to include `telemetry_counter_backend_fallback_total`.
- Added recording rule:
  - `openbrain_telemetry_backend_fallback_1h`
- Added alert:
  - `OpenBrainTelemetryBackendFallbackDetected`
- Updated governance technical debt wording from missing visibility to alert tuning.

## Risk

- Low: additive monitoring-only change.
- Operational: alert may trigger during controlled restart windows if fallback is expected.

## Validation

- `python3 scripts/validate_monitoring_contract.py`
- `make pr-readiness`

## Files

- `monitoring/contracts/openbrain-metrics-contract.json`
- `monitoring/prometheus/openbrain-alerts.yml`
- `docs/governance-layer.md`
