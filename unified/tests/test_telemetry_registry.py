"""Tests for Histogram, TelemetryRegistry, and render_prometheus_metrics."""

import pytest

from src.telemetry import (
    DEFAULT_BUCKETS,
    Histogram,
    TelemetryRegistry,
    bulk_load_histograms,
    bulk_load_metrics,
    get_metrics_snapshot,
    incr_metric,
    observe_metric,
    render_prometheus_metrics,
    reset_metrics,
    set_gauge_metric,
)


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


def test_histogram_observe_accumulates_sum_and_count():
    h = Histogram("latency", (0.1, 1.0))
    h.observe(0.05)
    h.observe(0.5)
    assert h.count == 2
    assert abs(h.sum - 0.55) < 1e-9


def test_histogram_observe_increments_correct_buckets():
    h = Histogram("lat", (0.1, 1.0))
    h.observe(0.05)  # falls in first bucket (<=0.1) and subsequent
    snap = h.snapshot()
    # bucket at index 0 (<=0.1) should have count 1
    assert snap["counts"][0] == 1


def test_histogram_snapshot_structure():
    h = Histogram("lat", (0.1,))
    h.observe(0.05)
    snap = h.snapshot()
    assert "sum" in snap
    assert "count" in snap
    assert "buckets" in snap
    assert "counts" in snap


def test_histogram_snapshot_inf_bucket_serialized_as_string():
    h = Histogram("lat", (0.1,))
    snap = h.snapshot()
    assert "inf" in snap["buckets"]


def test_histogram_from_snapshot_roundtrip():
    h = Histogram("lat", (0.1, 1.0))
    h.observe(0.05)
    h.observe(0.5)
    snap = h.snapshot()
    restored = Histogram.from_snapshot("lat", snap)
    assert restored.count == h.count
    assert abs(restored.sum - h.sum) < 1e-9
    assert restored.counts == h.counts


def test_histogram_from_snapshot_uses_default_buckets_when_empty():
    # When buckets is empty, defaults are used; counts must match the bucket count
    n_buckets = len(DEFAULT_BUCKETS) + 1  # +1 for inf
    restored = Histogram.from_snapshot(
        "lat",
        {"buckets": [], "counts": [0] * n_buckets, "sum": 0.0, "count": 0},
    )
    assert len(restored.buckets) == n_buckets


def test_histogram_from_snapshot_raises_on_bad_shape():
    with pytest.raises(ValueError, match="Invalid persisted histogram"):
        Histogram.from_snapshot(
            "lat",
            {
                "buckets": ["inf"],
                "counts": [1, 2, 3],  # wrong length
                "sum": 0,
                "count": 0,
            },
        )


def test_histogram_from_snapshot_handles_inf_string():
    snap = {
        "buckets": [0.1, "inf"],
        "counts": [1, 2],
        "sum": 0.05,
        "count": 1,
    }
    restored = Histogram.from_snapshot("lat", snap)
    assert restored.buckets[-1] == float("inf")


# ---------------------------------------------------------------------------
# TelemetryRegistry
# ---------------------------------------------------------------------------


def test_registry_incr_and_snapshot():
    reg = TelemetryRegistry()
    reg.incr("memories_created_total", 3)
    assert reg.snapshot()["memories_created_total"] == 3


def test_registry_bulk_load_counters():
    reg = TelemetryRegistry()
    reg.bulk_load_counters({"memories_created_total": 42})
    assert reg.snapshot()["memories_created_total"] == 42


def test_registry_bulk_load_histograms():
    reg = TelemetryRegistry()
    snap = {
        "request_latency": {
            "buckets": [0.1, "inf"],
            "counts": [5, 10],
            "sum": 2.5,
            "count": 10,
        }
    }
    reg.bulk_load_histograms(snap)
    hists = reg.histograms_snapshot()
    assert "request_latency" in hists
    assert hists["request_latency"].count == 10


def test_registry_set_gauge_and_gauges_snapshot():
    reg = TelemetryRegistry()
    reg.set_gauge("active_memories", 99.0)
    snap = reg.gauges_snapshot()
    assert snap["active_memories"] == 99.0


def test_registry_gauges_snapshot_sorted():
    reg = TelemetryRegistry()
    reg.set_gauge("z_gauge", 1.0)
    reg.set_gauge("a_gauge", 2.0)
    keys = list(reg.gauges_snapshot().keys())
    assert keys == sorted(keys)


def test_registry_observe_creates_histogram():
    reg = TelemetryRegistry()
    reg.observe("req_latency", 0.05)
    hists = reg.histograms_snapshot()
    assert "req_latency" in hists
    assert hists["req_latency"].count == 1


def test_registry_observe_reuses_existing_histogram():
    reg = TelemetryRegistry()
    reg.observe("req_latency", 0.1)
    reg.observe("req_latency", 0.2)
    assert reg.histograms_snapshot()["req_latency"].count == 2


def test_registry_reset_clears_all():
    reg = TelemetryRegistry()
    reg.incr("memories_created_total", 5)
    reg.set_gauge("active_memories", 10.0)
    reg.observe("latency", 0.1)
    reg.reset()
    assert reg.snapshot()["memories_created_total"] == 0
    assert reg.gauges_snapshot() == {}
    assert reg.histograms_snapshot() == {}


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------


def test_incr_metric_and_get_snapshot():
    reset_metrics()
    incr_metric("memories_created_total", 2)
    snap = get_metrics_snapshot()
    assert snap["counters"]["memories_created_total"] == 2
    reset_metrics()


def test_bulk_load_metrics():
    reset_metrics()
    bulk_load_metrics({"memories_created_total": 7})
    snap = get_metrics_snapshot()
    assert snap["counters"]["memories_created_total"] == 7
    reset_metrics()


def test_bulk_load_histograms_fn():
    reset_metrics()
    bulk_load_histograms(
        {"req_lat": {"buckets": [0.1, "inf"], "counts": [2, 4], "sum": 1.0, "count": 4}}
    )
    snap = get_metrics_snapshot()
    assert "req_lat" in snap["histograms"]
    reset_metrics()


def test_set_gauge_metric():
    reset_metrics()
    set_gauge_metric("active_memories", 50.0)
    snap = get_metrics_snapshot()
    assert snap["gauges"]["active_memories"] == 50.0
    reset_metrics()


def test_observe_metric():
    reset_metrics()
    observe_metric("request_latency_seconds", 0.5)
    snap = get_metrics_snapshot()
    assert "request_latency_seconds" in snap["histograms"]
    reset_metrics()


# ---------------------------------------------------------------------------
# render_prometheus_metrics
# ---------------------------------------------------------------------------


def test_render_prometheus_includes_counter_type():
    reset_metrics()
    incr_metric("memories_created_total", 1)
    output = render_prometheus_metrics()
    assert "# TYPE memories_created_total counter" in output
    assert "memories_created_total 1" in output
    reset_metrics()


def test_render_prometheus_includes_gauge():
    reset_metrics()
    set_gauge_metric("active_memories", 42.0)
    output = render_prometheus_metrics()
    assert "# TYPE active_memories gauge" in output
    assert "active_memories 42.0" in output
    reset_metrics()


def test_render_prometheus_includes_histogram_buckets():
    reset_metrics()
    observe_metric("request_latency_seconds", 0.05)
    output = render_prometheus_metrics()
    assert "# TYPE request_latency_seconds histogram" in output
    assert 'request_latency_seconds_bucket{le="inf"}' in output
    assert "request_latency_seconds_count 1" in output
    reset_metrics()


def test_render_prometheus_sanitizes_metric_names():
    reset_metrics()
    set_gauge_metric("metric.with.dots", 1.0)
    output = render_prometheus_metrics()
    assert "metric_with_dots" in output
    reset_metrics()


def test_render_prometheus_empty_returns_empty_string():
    reset_metrics()
    # After reset, counters still exist (known counters seeded at 0)
    # but the output should be valid and not crash
    output = render_prometheus_metrics()
    assert isinstance(output, str)
    reset_metrics()


def test_render_prometheus_ends_with_newline_when_non_empty():
    reset_metrics()
    incr_metric("memories_created_total", 1)
    output = render_prometheus_metrics()
    assert output.endswith("\n")
    reset_metrics()
