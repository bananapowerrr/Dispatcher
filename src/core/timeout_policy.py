# -*- coding: utf-8 -*-
"""Unified timeout formulas for exec + stuck reclaim (offline-safe).

Keeps executor hard-cap and reclaim adaptive lease in one place so complexity /
worker class affect both sides consistently.
"""
from __future__ import annotations

import os
from typing import Any


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default)) or default))
    except (TypeError, ValueError):
        return max(minimum, default)


# Exec (subprocess / aider / ollama)
EXEC_HARD_CAP = _env_int("AGENTBUS_EXEC_HARD_CAP", 1800, minimum=60)
EXEC_MIN = 15

# Stuck / reclaim lease
STUCK_BASE = _env_int("AGENTBUS_STUCK_BASE_SEC", 300, minimum=60)
STUCK_MAX = _env_int("AGENTBUS_STUCK_TIMEOUT_MAX", 1800, minimum=STUCK_BASE)

_COMPLEXITY_FACTOR: dict[int, float] = {
    1: 0.8,
    2: 1.0,
    3: 1.5,
    4: 2.2,
    5: 3.0,
}

_WORKER_HINTS: tuple[tuple[str, float], ...] = (
    ("opencode", 1.4),
    ("big", 1.3),
    ("local", 1.1),
    ("aider", 1.0),
    ("mock", 0.5),
)


def clamp_exec_timeout(timeout: int | float | None) -> int:
    """Bound worker timeout into [EXEC_MIN, EXEC_HARD_CAP]."""
    try:
        t = int(timeout)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        t = 300
    return max(EXEC_MIN, min(t, EXEC_HARD_CAP))


def worker_class_factor(worker: str | None) -> float:
    name = (worker or "").lower()
    for hint, factor in _WORKER_HINTS:
        if hint in name:
            return factor
    return 1.0


def complexity_factor(complexity: int | None) -> float:
    try:
        c = max(1, min(5, int(complexity or 2)))
    except (TypeError, ValueError):
        c = 2
    return _COMPLEXITY_FACTOR.get(c, 1.5)


def suggest_exec_timeout(
    *,
    worker_timeout: int | None = None,
    complexity: int | None = None,
    worker: str | None = None,
    multi_step: bool = False,
) -> int:
    """Recommended subprocess timeout for a task."""
    base = int(worker_timeout) if worker_timeout else 300
    try:
        base = int(base)
    except (TypeError, ValueError):
        base = 300
    factor = complexity_factor(complexity) * worker_class_factor(worker)
    bonus = 120 if multi_step else 0
    return clamp_exec_timeout(int(base * factor) + bonus)


def stuck_timeout_sec(
    raw: dict[str, Any] | None = None,
    *,
    base_sec: float | None = None,
    max_sec: float | None = None,
    worker: str | None = None,
    complexity: int | None = None,
) -> float:
    """Adaptive reclaim lease (seconds). Prefer this over ad-hoc math."""
    base = float(base_sec if base_sec is not None else STUCK_BASE)
    cap = float(max_sec if max_sec is not None else STUCK_MAX)
    raw = raw if isinstance(raw, dict) else {}
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}

    explicit = meta.get("stuck_timeout_sec") or raw.get("stuck_timeout_sec")
    if explicit is not None:
        try:
            return max(60.0, min(cap, float(explicit)))
        except (TypeError, ValueError):
            pass

    if complexity is None:
        try:
            from core.router import task_complexity

            complexity = task_complexity(raw)
        except Exception:
            complexity = int(meta.get("complexity") or raw.get("complexity") or 2)

    factor = complexity_factor(complexity)
    w = worker or str(raw.get("worker") or meta.get("worker") or raw.get("executor") or "")
    factor *= worker_class_factor(w)

    bonus = 0.0
    if meta.get("pev") or meta.get("pev_plan") or raw.get("pev"):
        bonus += 180.0
    if meta.get("multi_step") or meta.get("subtasks"):
        bonus += 120.0

    timeout = base * factor + bonus
    return max(60.0, min(cap, timeout))
