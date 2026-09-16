# -*- coding: utf-8 -*-
"""Unified fallback policy — cloud fail → next → local (mass-product).

Does not replace the worker loop in Runtime; ranks and filters candidates
so Decision Engine prefers local after network/billing failures and skips
cloud when offline.
"""
from __future__ import annotations

import os
import socket
from typing import Any


# Error classes that should trigger backend switch (not just retry same)
_RATE = ("429", "rate limit", "rate_limit", "too many requests", "quota exceeded")
_BILLING = ("402", "payment required", "insufficient credits", "billing", "no credits")
_AUTH = ("401", "403", "invalid api key", "unauthorized", "forbidden")
_NET = (
    "connection refused", "connection reset", "timed out", "timeout",
    "name or service not known", "temporary failure", "network is unreachable",
    "failed to establish", "max retries exceeded", "connect error",
    "ssl", "proxy", "unreachable",
)
_MODEL = ("model not found", "unknown model", "does not exist", "invalid model")


def classify_failure(error: str | None, *, timed_out: bool = False) -> str:
    """Return: rate_limit | billing | auth | network | timeout | model | other."""
    if timed_out:
        return "timeout"
    text = (error or "").lower()
    if not text:
        return "other"
    for s in _BILLING:
        if s in text:
            return "billing"
    for s in _RATE:
        if s in text:
            return "rate_limit"
    for s in _AUTH:
        if s in text:
            return "auth"
    for s in _MODEL:
        if s in text:
            return "model"
    for s in _NET:
        if s in text:
            return "network"
    return "other"


def should_switch_backend(kind: str) -> bool:
    """Whether to try another worker/backend instead of same one."""
    return kind in ("rate_limit", "billing", "auth", "network", "timeout", "model")


def prefer_local_after(kind: str) -> bool:
    """After these failures, local backends should rank higher."""
    return kind in ("rate_limit", "billing", "auth", "network", "timeout")


def is_offline(timeout: float = 1.5) -> bool:
    """Best-effort: no route to public DNS / forced env."""
    force = (os.getenv("AGENTBUS_OFFLINE") or "").strip().lower()
    if force in ("1", "true", "yes", "on"):
        return True
    if force in ("0", "false", "no", "off"):
        return False
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("1.1.1.1", 53))
        return False
    except OSError:
        return True
    finally:
        socket.setdefaulttimeout(None)


def _provider_of(worker: Any) -> str:
    return str(getattr(worker, "provider", "") or "").lower()


def is_local_worker(worker: Any) -> bool:
    return _provider_of(worker) in ("ollama", "lmstudio", "local", "")


def filter_for_offline(workers: list[Any], *, offline: bool | None = None) -> list[Any]:
    """If offline, drop cloud providers."""
    if offline is None:
        offline = is_offline()
    if not offline:
        return list(workers)
    return [w for w in workers if is_local_worker(w)]


def order_candidates(
    workers: list[Any],
    *,
    tried: list[str] | None = None,
    failure_kind: str | None = None,
    offline: bool | None = None,
) -> list[Any]:
    """Stable ranking for fallback: local first after cloud pain / offline."""
    tried_set = set(tried or [])
    pool = [w for w in workers if getattr(w, "name", None) not in tried_set]
    pool = filter_for_offline(pool, offline=offline)

    local_boost = prefer_local_after(failure_kind or "")

    def key(w: Any) -> tuple:
        local = is_local_worker(w)
        # lower = better
        # after billing/network: local first; else keep mild local preference
        if local_boost:
            tier = 0 if local else 1
        else:
            tier = 0 if local else 2
        prio = int(getattr(w, "priority", 100) or 100)
        wtier = int(getattr(w, "tier", 5) or 5)
        return (tier, prio, wtier, str(getattr(w, "name", "")))

    return sorted(pool, key=key)


def next_fallback(
    workers: list[Any],
    tried: list[str],
    *,
    error: str | None = None,
    timed_out: bool = False,
    offline: bool | None = None,
) -> Any | None:
    """Pick next worker after a failure, or None if exhausted."""
    kind = classify_failure(error, timed_out=timed_out)
    if not should_switch_backend(kind) and tried:
        # soft failures: still allow switch but weaker local bias
        kind = kind or "other"
    ordered = order_candidates(
        workers, tried=tried, failure_kind=kind, offline=offline
    )
    return ordered[0] if ordered else None
