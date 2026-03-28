from __future__ import annotations

from collections import Counter
from threading import Lock
from typing import Any


class TelemetryRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[str] = Counter()
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
