from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Any

# Pre-initialize all counters to 0 so Prometheus sees them from the first scrape.
# Without this, Python Counter omits zero-value keys and Prometheus has no series
# to evaluate rate() / record history against after a server restart.
KNOWN_COUNTERS: tuple[str, ...] = (
    "memories_created_total",
    "memories_updated_total",
    "memories_versioned_total",
    "memories_skipped_total",
    "memories_deleted_total",
    "bulk_batches_total",
    "bulk_records_total",
    "search_requests_total",
    "search_zero_hit_total",
    "get_context_requests_total",
    "sync_checks_total",
    "sync_synced_total",
    "sync_missing_total",
    "sync_outdated_total",
    "sync_exists_total",
    "exports_total",
    "maintain_runs_total",
    "duplicate_candidates_total",
    "orphaned_supersession_links_total",
    "owner_normalizations_total",
    "policy_skip_total",
    "policy_skip_dedup_total",
    "policy_skip_delete_total",
    "policy_skip_owner_normalization_total",
    "policy_skip_link_repair_total",
    "dedup_override_total",
    "duplicate_risk_writes_total",
    "access_denied_total",
    "access_denied_admin_total",
    "access_denied_domain_total",
    "access_denied_owner_total",
    "access_denied_tenant_total",
)


class TelemetryRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[str] = Counter()
        # Pre-seed known counters so they appear in /metrics from first scrape.
        self._counters.update({name: 0 for name in KNOWN_COUNTERS})
        self._gauges: dict[str, float] = {}

    def incr(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counters.items()))

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def gauges_snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(sorted(self._gauges.items()))

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._counters.update({name: 0 for name in KNOWN_COUNTERS})
            self._gauges.clear()


registry = TelemetryRegistry()


def incr_metric(name: str, value: int = 1) -> None:
    registry.incr(name, value)


def get_metrics_snapshot() -> dict[str, Any]:
    return {"counters": registry.snapshot(), "gauges": registry.gauges_snapshot()}


def reset_metrics() -> None:
    registry.reset()


def set_gauge_metric(name: str, value: float) -> None:
    registry.set_gauge(name, value)


def _sanitize_metric_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)


def render_prometheus_metrics() -> str:
    lines: list[str] = []
    for name, value in registry.snapshot().items():
        metric_name = _sanitize_metric_name(name)
        lines.append(f"# TYPE {metric_name} counter")
        lines.append(f"{metric_name} {value}")
    for name, value in registry.gauges_snapshot().items():
        metric_name = _sanitize_metric_name(name)
        lines.append(f"# TYPE {metric_name} gauge")
        lines.append(f"{metric_name} {value}")
    return "\n".join(lines) + ("\n" if lines else "")
