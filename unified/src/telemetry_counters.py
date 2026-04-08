from __future__ import annotations

import os
from collections import Counter
from threading import Lock
from typing import Protocol


class CounterBackend(Protocol):
    def incr(self, name: str, value: int = 1) -> None: ...
    def snapshot(self) -> dict[str, int]: ...
    def bulk_load(self, values: dict[str, int]) -> None: ...
    def reset(self) -> None: ...


class InMemoryCounterBackend:
    def __init__(self, known_counters: tuple[str, ...]) -> None:
        self._known_counters = known_counters
        self._lock = Lock()
        self._counters: Counter[str] = Counter()
        self._seed()

    def _seed(self) -> None:
        self._counters.update({name: 0 for name in self._known_counters})

    def incr(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(sorted(self._counters.items()))

    def bulk_load(self, values: dict[str, int]) -> None:
        with self._lock:
            for name, val in values.items():
                if name in self._known_counters or name.startswith("http_requests_total_"):
                    self._counters[name] = val

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._seed()


class RedisCounterBackend:
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
            raise RuntimeError("redis package is required for TELEMETRY_BACKEND=redis") from exc

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
        self._client.hincrby(self._hash_key, name, value)

    def snapshot(self) -> dict[str, int]:
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
        if not values:
            return
        pipe = self._client.pipeline(transaction=False)
        for name, val in values.items():
            if name in self._known_counters or name.startswith("http_requests_total_"):
                pipe.hset(self._hash_key, name, int(val))
        pipe.execute()

    def reset(self) -> None:
        self._client.delete(self._hash_key)
        self._seed()


def build_counter_backend(known_counters: tuple[str, ...]) -> CounterBackend:
    backend = os.getenv("TELEMETRY_BACKEND", "memory").strip().lower()
    if backend != "redis":
        return InMemoryCounterBackend(known_counters)

    redis_url = (
        os.getenv("TELEMETRY_REDIS_URL")
        or os.getenv("REDIS_URL")
        or ""
    ).strip()
    if not redis_url:
        return InMemoryCounterBackend(known_counters)

    try:
        return RedisCounterBackend(
            redis_url=redis_url,
            known_counters=known_counters,
        )
    except Exception:
        return InMemoryCounterBackend(known_counters)
