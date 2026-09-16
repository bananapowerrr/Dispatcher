# -*- coding: utf-8 -*-
"""Performance helpers: TTL cache, timing, simple memoization.

Offline-safe utilities for AgentBus. No hard dependency on runtime loop.
"""
from __future__ import annotations

import functools
import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Generic, Hashable, TypeVar

logger = logging.getLogger("agentbus.performance")

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")

# Defaults (override via env if needed)
CACHE_TTL_SEC: float = 300.0
INDEX_REBUILD_INTERVAL: float = 300.0
SLOW_THRESHOLD_SEC: float = 2.0


class _TTLEntry(Generic[T]):
    __slots__ = ("value", "expires")

    def __init__(self, value: T, ttl: float) -> None:
        self.value = value
        self.expires = time.monotonic() + max(0.0, ttl)


class TTLCache(Generic[T]):
    """Thread-safe dict with per-entry TTL and max size (FIFO eviction)."""

    def __init__(self, maxsize: int = 256, ttl: float = CACHE_TTL_SEC) -> None:
        self.maxsize = max(1, int(maxsize))
        self.ttl = float(ttl)
        self._data: dict[Hashable, _TTLEntry[T]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: Hashable, default: T | None = None) -> T | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return default
            if time.monotonic() > entry.expires:
                self._data.pop(key, None)
                self.misses += 1
                return default
            self.hits += 1
            return entry.value

    def set(self, key: Hashable, value: T, ttl: float | None = None) -> None:
        with self._lock:
            if key not in self._data and len(self._data) >= self.maxsize:
                # drop oldest by expiry
                oldest = min(self._data.items(), key=lambda kv: kv[1].expires)
                self._data.pop(oldest[0], None)
            self._data[key] = _TTLEntry(value, self.ttl if ttl is None else float(ttl))

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            total = self.hits + self.misses
            rate = (self.hits / total) if total else 0.0
            return {
                "size": len(self._data),
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(rate, 4),
            }


def cached_with_ttl(
    ttl: float = CACHE_TTL_SEC,
    maxsize: int = 128,
    key_fn: Callable[..., Hashable] | None = None,
) -> Callable[[F], F]:
    """Decorator: cache function results with TTL.

    Example::

        @cached_with_ttl(ttl=300)
        def get_project_index(project_path: str) -> dict:
            ...
    """
    cache: TTLCache[Any] = TTLCache(maxsize=maxsize, ttl=ttl)

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if key_fn is not None:
                key: Hashable = key_fn(*args, **kwargs)
            else:
                key = (args, tuple(sorted(kwargs.items())))
            hit = cache.get(key)
            if hit is not None:
                return hit
            result = fn(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper.cache = cache  # type: ignore[attr-defined]
        wrapper.cache_clear = cache.clear  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def measure_time(name: str | None = None, threshold: float = SLOW_THRESHOLD_SEC) -> Callable[[F], F]:
    """Decorator: log slow calls above *threshold* seconds."""

    def decorator(fn: F) -> F:
        label = name or getattr(fn, "__qualname__", getattr(fn, "__name__", "fn"))

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                dt = time.perf_counter() - t0
                if dt >= threshold:
                    logger.warning("slow %s took %.3fs", label, dt)

        return wrapper  # type: ignore[return-value]

    return decorator
