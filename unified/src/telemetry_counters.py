from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from threading import Lock
from typing import Protocol


class CounterBackend(Protocol):
    """Protocol for pluggable counter backends (in-memory or Redis)."""

    def incr(self, name: str, value: int = 1) -> None:
        """Increment a counter by value."""
        ...

    def snapshot(self) -> dict[str, int]:
        """Return all counter values as a name→count mapping."""
        ...

    def bulk_load(self, values: dict[str, int]) -> None:
        """Restore counter state from a persisted snapshot."""
        ...

    def reset(self) -> None:
        """Reset all counters to zero."""
        ...


@dataclass(frozen=True)
class CounterBackendBuildMeta:
    """Metadata about how the counter backend was selected or fell back."""

    requested_backend: str
    selected_backend: str
    fallback_reason: str | None = None


class InMemoryCounterBackend:
    """Thread-safe in-process counter backend backed by a Python Counter."""

    def __init__(self, known_counters: tuple[str, ...]) -> None:
        """Initialize the backend, pre-seeding all known counters to zero."""
        self._known_counters = known_counters
        self._lock = Lock()
        self._counters: Counter[str] = Counter()
        self._seed()

    def _seed(self) -> None:
        self._counters.update({name: 0 for name in self._known_counters})

    def incr(self, name: str, value: int = 1) -> None:
        """Increment the named counter by value under a lock."""
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        """Return all counter values sorted by name."""
        with self._lock:
            return dict(sorted(self._counters.items()))

    def bulk_load(self, values: dict[str, int]) -> None:
        """Restore known counters from a persisted snapshot, ignoring unknown names."""
        with self._lock:
            for name, val in values.items():
                if name in self._known_counters or name.startswith(
                    "http_requests_total_"
                ):
                    self._counters[name] = val

    def reset(self) -> None:
        """Clear all counters and re-seed known counters to zero."""
        with self._lock:
            self._counters.clear()
            self._seed()


class RedisCounterBackend:
    """Counter backend that persists and shares counters via a Redis hash."""

    def __init__(
        self,
        *,
        redis_url: str,
        known_counters: tuple[str, ...],
        redis_hash_key: str = "openbrain:telemetry:counters",
    ) -> None:
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError(
                "redis package is required for TELEMETRY_BACKEND=redis"
            ) from exc

        self._known_counters = known_counters
        self._hash_key = redis_hash_key
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        self._seed()

    def _seed(self) -> None:
        pipe = self._client.pipeline(transaction=False)
        for name in self._known_counters:
            pipe.hsetnx(self._hash_key, name, 0)
        pipe.execute()

    def incr(self, name: str, value: int = 1) -> None:
        """Atomically increment the named field in the Redis hash."""
        self._client.hincrby(self._hash_key, name, value)

    def snapshot(self) -> dict[str, int]:
        """Fetch all counter values from Redis, defaulting missing known counters to 0."""
        payload = self._client.hgetall(self._hash_key)
        result: dict[str, int] = {}
        for name, raw in payload.items():
            try:
                result[name] = int(raw)
            except (TypeError, ValueError):
                continue
        for name in self._known_counters:
            result.setdefault(name, 0)
        return dict(sorted(result.items()))

    def bulk_load(self, values: dict[str, int]) -> None:
        """Write counter values directly into Redis (used for restoring persisted state)."""
        if not values:
            return
        pipe = self._client.pipeline(transaction=False)
        for name, val in values.items():
            if name in self._known_counters or name.startswith("http_requests_total_"):
                pipe.hset(self._hash_key, name, int(val))
        pipe.execute()

    def reset(self) -> None:
        """Delete the Redis hash and re-seed known counters to zero."""
        self._client.delete(self._hash_key)
        self._seed()


def build_counter_backend(known_counters: tuple[str, ...]) -> CounterBackend:
    """Build a counter backend using environment config (memory or Redis)."""
    backend, _ = build_counter_backend_with_meta(known_counters)
    return backend


def build_counter_backend_with_meta(
    known_counters: tuple[str, ...],
) -> tuple[CounterBackend, CounterBackendBuildMeta]:
    """Build a counter backend and return it with selection metadata.

    Selects Redis if TELEMETRY_BACKEND=redis and a valid URL is available;
    falls back to in-memory with a reason recorded in the metadata.
    """
    requested_backend = os.getenv("TELEMETRY_BACKEND", "memory").strip().lower()
    if requested_backend != "redis":
        return InMemoryCounterBackend(known_counters), CounterBackendBuildMeta(
            requested_backend=requested_backend,
            selected_backend="memory",
            fallback_reason=None,
        )

    redis_url = (
        os.getenv("TELEMETRY_REDIS_URL") or os.getenv("REDIS_URL") or ""
    ).strip()
    if not redis_url:
        return InMemoryCounterBackend(known_counters), CounterBackendBuildMeta(
            requested_backend=requested_backend,
            selected_backend="memory",
            fallback_reason="redis_url_missing",
        )

    try:
        return RedisCounterBackend(
            redis_url=redis_url,
            known_counters=known_counters,
        ), CounterBackendBuildMeta(
            requested_backend=requested_backend,
            selected_backend="redis",
            fallback_reason=None,
        )
    except Exception as exc:
        return InMemoryCounterBackend(known_counters), CounterBackendBuildMeta(
            requested_backend=requested_backend,
            selected_backend="memory",
            fallback_reason=f"redis_unavailable:{exc.__class__.__name__}",
        )
