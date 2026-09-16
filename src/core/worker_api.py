# -*- coding: utf-8 -*-
"""Unified Worker API (Stage 4) — interface over concrete CLI/LLM workers.

Existing `core.workers.Worker` remains the config record.
Adapters implement execute() so Router/Runtime do not depend on harness details.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class WorkerResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    latency: float = 0.0
    tokens: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_exec(cls, result: Any) -> "WorkerResult":
        """Adapt legacy exec result objects."""
        return cls(
            ok=bool(getattr(result, "ok", False)),
            stdout=str(getattr(result, "stdout", "") or ""),
            stderr=str(getattr(result, "stderr", "") or ""),
            latency=float(getattr(result, "latency", 0.0) or 0.0),
            tokens=int(getattr(result, "tokens", 0) or 0),
            meta=dict(getattr(result, "meta", None) or {}),
        )


@runtime_checkable
class WorkerBackend(Protocol):
    """Minimal contract for an execution backend."""

    name: str

    def can_handle(self, task: Any) -> bool:
        ...

    def execute(self, task: Any, *, context: Any = None) -> WorkerResult:
        ...


@dataclass
class ConfigWorkerAdapter:
    """Wraps core.workers.Worker + Runtime._exec_worker style callable.

    Runtime still owns the real subprocess path; this adapter is the
    stable boundary for Router scoring and future native backends.
    """

    worker: Any
    exec_fn: Any = None  # callable(worker, task, ctx) -> legacy result

    @property
    def name(self) -> str:
        return str(getattr(self.worker, "name", "unknown"))

    def can_handle(self, task: Any) -> bool:
        if not getattr(self.worker, "enabled", True):
            return False
        # tier vs complexity
        try:
            complexity = int(getattr(task, "complexity", None) or (getattr(task, "metadata", {}) or {}).get("complexity") or 2)
        except (TypeError, ValueError):
            complexity = 2
        tier = int(getattr(self.worker, "tier", 5) or 5)
        # weak models should not take complexity >= 4 unless no alternative (router decides)
        min_tier = {1: 1, 2: 2, 3: 4, 4: 6, 5: 7}.get(min(5, max(1, complexity)), 5)
        return tier >= min_tier - 2  # soft: allow near-miss for fallback

    def execute(self, task: Any, *, context: Any = None) -> WorkerResult:
        if self.exec_fn is None:
            return WorkerResult(ok=False, stderr="no exec_fn bound")
        raw = self.exec_fn(self.worker, task, context)
        return WorkerResult.from_exec(raw)


def score_worker(
    worker: Any,
    task: Any,
    *,
    health_penalty: float = 0.0,
    cost_weight: float = 0.1,
    load: float = 0.0,
) -> float:
    """Higher is better. Used by Router-style ranking."""
    tier = float(getattr(worker, "tier", 5) or 5)
    quality = float(getattr(worker, "quality", 1.0) or 1.0)
    priority = float(getattr(worker, "priority", 100) or 100)
    # lower priority number = better in YAML; invert
    priority_score = max(0.0, 200.0 - priority) / 200.0
    cost = 1.0 if getattr(worker, "provider", "local") == "local" else 3.0
    try:
        complexity = int(getattr(task, "complexity", 2) or 2)
    except (TypeError, ValueError):
        complexity = 2
    capability = min(1.0, tier / 10.0) * (1.0 if tier >= complexity else 0.5)
    score = (
        capability * 40.0
        + quality * 20.0
        + priority_score * 15.0
        - cost * cost_weight * 10.0
        - health_penalty * 25.0
        - load * 10.0
    )
    return score
