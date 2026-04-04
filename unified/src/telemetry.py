from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Any

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
)

# Standard Prometheus buckets for request latency (in seconds)
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)


class Histogram:
    def __init__(self, name: str, buckets: tuple[float, ...] = DEFAULT_BUCKETS) -> None:
        self.name = name
        self.buckets = sorted(buckets) + [float("inf")]
        self.counts = [0] * len(self.buckets)
        self.sum = 0.0
        self.count = 0

    def observe(self, value: float) -> None:
        self.sum += value
        self.count += 1
        for i, bucket in enumerate(self.buckets):
            if value <= bucket:
                self.counts[i] += 1

    def snapshot(self) -> dict[str, Any]:
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
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[str] = Counter()
        # Pre-seed known counters so they appear in /metrics from first scrape.
        self._counters.update({name: 0 for name in KNOWN_COUNTERS})
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, Histogram] = {}

    def incr(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counters.items()))

    def bulk_load_counters(self, values: dict[str, int]) -> None:
        with self._lock:
            for name, val in values.items():
                # We only load values for known counters to avoid bloat from old/deleted metrics
                if name in KNOWN_COUNTERS or name.startswith("http_requests_total_"):
                    self._counters[name] = val

    def bulk_load_histograms(self, values: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            for name, payload in values.items():
                self._histograms[name] = Histogram.from_snapshot(name, payload)

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def gauges_snapshot(self) -> dict[str, float]:
        with self._lock:
            return dict(sorted(self._gauges.items()))

    def observe(self, name: str, value: float, buckets: tuple[float, ...] = DEFAULT_BUCKETS) -> None:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, buckets)
            self._histograms[name].observe(value)

    def histograms_snapshot(self) -> dict[str, Histogram]:
        with self._lock:
            return {
                name: Histogram.from_snapshot(name, hist.snapshot())
                for name, hist in self._histograms.items()
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._counters.update({name: 0 for name in KNOWN_COUNTERS})
            self._gauges.clear()
            self._histograms.clear()


registry = TelemetryRegistry()


def incr_metric(name: str, value: int = 1) -> None:
    registry.incr(name, value)


def bulk_load_metrics(values: dict[str, int]) -> None:
    registry.bulk_load_counters(values)


def bulk_load_histograms(values: dict[str, dict[str, Any]]) -> None:
    registry.bulk_load_histograms(values)


def get_metrics_snapshot() -> dict[str, Any]:
    return {
        "counters": registry.snapshot(),
        "gauges": registry.gauges_snapshot(),
        "histograms": {
            name: hist.snapshot() for name, hist in registry.histograms_snapshot().items()
        },
    }


def reset_metrics() -> None:
    registry.reset()


def set_gauge_metric(name: str, value: float) -> None:
    registry.set_gauge(name, value)


def observe_metric(name: str, value: float, buckets: tuple[float, ...] = DEFAULT_BUCKETS) -> None:
    registry.observe(name, value, buckets)


def _sanitize_metric_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)


def render_prometheus_metrics() -> str:
    lines: list[str] = []
    # Counters
    for name, value in registry.snapshot().items():
        metric_name = _sanitize_metric_name(name)
        lines.append(f"# TYPE {metric_name} counter")
        lines.append(f"{metric_name} {value}")

    # Gauges
    for name, value in registry.gauges_snapshot().items():
        metric_name = _sanitize_metric_name(name)
        lines.append(f"# TYPE {metric_name} gauge")
        lines.append(f"{metric_name} {value}")

    # Histograms
    for name, hist in registry.histograms_snapshot().items():
        metric_name = _sanitize_metric_name(name)
        lines.append(f"# TYPE {metric_name} histogram")
        cumulative_count = 0
        for i, bucket in enumerate(hist.buckets):
            cumulative_count += hist.counts[i]
            upper_bound = "inf" if bucket == float("inf") else str(bucket)
            lines.append(f'{metric_name}_bucket{{le="{upper_bound}"}} {cumulative_count}')
        lines.append(f"{metric_name}_count {hist.count}")
        lines.append(f"{metric_name}_sum {hist.sum}")

    return "\n".join(lines) + ("\n" if lines else "")
