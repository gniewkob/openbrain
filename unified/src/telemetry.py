from __future__ import annotations

from threading import Lock
from typing import Any

from .telemetry_counters import build_counter_backend_with_meta

# Pre-initialize all counters to 0 so Prometheus sees them from the first scrape.
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
    "http_requests_total_200",
    "http_requests_total_201",
    "http_requests_total_204",
    "http_requests_total_400",
    "http_requests_total_401",
    "http_requests_total_403",
    "http_requests_total_404",
    "http_requests_total_422",
    "http_requests_total_500",
    "http_requests_total_502",
    "http_requests_total_503",
    "telemetry_counter_backend_fallback_total",
)

# Standard Prometheus buckets for request latency (in seconds)
DEFAULT_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
)


class Histogram:
    """In-process histogram for tracking value distributions (e.g. request latency)."""

    def __init__(self, name: str, buckets: tuple[float, ...] = DEFAULT_BUCKETS) -> None:
        """Initialize a histogram with the given name and bucket boundaries."""
        self.name = name
        self.buckets = sorted(buckets) + [float("inf")]
        self.counts = [0] * len(self.buckets)
        self.sum = 0.0
        self.count = 0

    def observe(self, value: float) -> None:
        """Record a single observation into the histogram."""
        self.sum += value
        self.count += 1
        for i, bucket in enumerate(self.buckets):
            if value <= bucket:
                self.counts[i] += 1

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable snapshot of the current histogram state."""
        return {
            "sum": self.sum,
            "count": self.count,
            "buckets": [
                "inf" if bucket == float("inf") else bucket for bucket in self.buckets
            ],
            "counts": list(self.counts),
        }

    @classmethod
    def from_snapshot(cls, name: str, data: dict[str, Any]) -> "Histogram":
        """Reconstruct a Histogram from a previously serialized snapshot."""
        raw_buckets = list(data.get("buckets") or [])
        finite_buckets = tuple(
            float(bucket)
            for bucket in raw_buckets
            if bucket not in {"inf", float("inf")}
        )
        histogram = cls(name, finite_buckets or DEFAULT_BUCKETS)
        counts = [int(value) for value in list(data.get("counts") or [])]
        if len(counts) != len(histogram.buckets):
            raise ValueError(f"Invalid persisted histogram shape for {name}")
        histogram.counts = counts
        histogram.sum = float(data.get("sum", 0.0))
        histogram.count = int(data.get("count", 0))
        return histogram


class TelemetryRegistry:
    """Thread-safe in-process registry for counters, gauges, and histograms."""

    def __init__(self) -> None:
        """Initialize the registry with pre-seeded known counters."""
        self._lock = Lock()
        self._counter_backend, self._counter_backend_meta = (
            build_counter_backend_with_meta(KNOWN_COUNTERS)
        )
        if self._counter_backend_meta.fallback_reason is not None:
            self._counter_backend.incr("telemetry_counter_backend_fallback_total", 1)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, Histogram] = {}

    def incr(self, name: str, value: int = 1) -> None:
        """Increment a named counter by the given value."""
        self._counter_backend.incr(name, value)

    def snapshot(self) -> dict[str, int]:
        """Return the current counter values as a name→count mapping."""
        return self._counter_backend.snapshot()

    def bulk_load_counters(self, values: dict[str, int]) -> None:
        """Restore counter state from a previously persisted snapshot."""
        self._counter_backend.bulk_load(values)

    def bulk_load_histograms(self, values: dict[str, dict[str, Any]]) -> None:
        """Restore histogram state from previously persisted snapshots."""
        with self._lock:
            for name, payload in values.items():
                self._histograms[name] = Histogram.from_snapshot(name, payload)

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge metric to an absolute value."""
        with self._lock:
            self._gauges[name] = value

    def gauges_snapshot(self) -> dict[str, float]:
        """Return all current gauge values sorted by name."""
        with self._lock:
            return dict(sorted(self._gauges.items()))

    def observe(
        self, name: str, value: float, buckets: tuple[float, ...] = DEFAULT_BUCKETS
    ) -> None:
        """Record a histogram observation for the named metric."""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, buckets)
            self._histograms[name].observe(value)

    def histograms_snapshot(self) -> dict[str, Histogram]:
        """Return deep copies of all current histograms, safe for serialization."""
        with self._lock:
            return {
                name: Histogram.from_snapshot(name, hist.snapshot())
                for name, hist in self._histograms.items()
            }

    def reset(self) -> None:
        """Reset all counters, gauges, and histograms to zero (useful in tests)."""
        self._counter_backend.reset()
        with self._lock:
            self._gauges.clear()
            self._histograms.clear()


registry = TelemetryRegistry()


def incr_metric(name: str, value: int = 1) -> None:
    """Increment a named counter in the global registry."""
    registry.incr(name, value)


def bulk_load_metrics(values: dict[str, int]) -> None:
    """Restore counter state into the global registry from a persisted snapshot."""
    registry.bulk_load_counters(values)


def bulk_load_histograms(values: dict[str, dict[str, Any]]) -> None:
    """Restore histogram state into the global registry from persisted snapshots."""
    registry.bulk_load_histograms(values)


def get_metrics_snapshot() -> dict[str, Any]:
    """Return a complete snapshot of all counters, gauges, and histograms."""
    return {
        "counters": registry.snapshot(),
        "gauges": registry.gauges_snapshot(),
        "histograms": {
            name: hist.snapshot()
            for name, hist in registry.histograms_snapshot().items()
        },
    }


def reset_metrics() -> None:
    """Reset the global metrics registry (used in tests)."""
    registry.reset()


def set_gauge_metric(name: str, value: float) -> None:
    """Set a gauge metric to an absolute value in the global registry."""
    registry.set_gauge(name, value)


def observe_metric(
    name: str, value: float, buckets: tuple[float, ...] = DEFAULT_BUCKETS
) -> None:
    """Record a histogram observation in the global registry."""
    registry.observe(name, value, buckets)


def _sanitize_metric_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)


def render_prometheus_metrics() -> str:
    """Render all metrics as a Prometheus-format text exposition string."""
    lines: list[str] = []
    # Counters
    for name, value in registry.snapshot().items():
        metric_name = _sanitize_metric_name(name)
        lines.append(f"# TYPE {metric_name} counter")
        lines.append(f"{metric_name} {value}")

    # Gauges
    for name, gvalue in registry.gauges_snapshot().items():
        metric_name = _sanitize_metric_name(name)
        lines.append(f"# TYPE {metric_name} gauge")
        lines.append(f"{metric_name} {gvalue}")

    # Histograms
    for name, hist in registry.histograms_snapshot().items():
        metric_name = _sanitize_metric_name(name)
        lines.append(f"# TYPE {metric_name} histogram")
        cumulative_count = 0
        for i, bucket in enumerate(hist.buckets):
            cumulative_count += hist.counts[i]
            upper_bound = "inf" if bucket == float("inf") else str(bucket)
            lines.append(
                f'{metric_name}_bucket{{le="{upper_bound}"}} {cumulative_count}'
            )
        lines.append(f"{metric_name}_count {hist.count}")
        lines.append(f"{metric_name}_sum {hist.sum}")

    return "\n".join(lines) + ("\n" if lines else "")
