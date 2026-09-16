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
    """Canonical worker outcome (FC-14).

    Bridges:
      ExecutionResult (subprocess) → WorkerResult → task result JSON → TaskResult
    """

    ok: bool
    stdout: str = ""
    stderr: str = ""
    latency: float = 0.0
    tokens: int = 0
    error: str = ""
    files_changed: list[str] = field(default_factory=list)
    patch: str = ""
    worker: str = ""
    timed_out: bool = False
    exit_code: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_exec(cls, result: Any) -> "WorkerResult":
        """Adapt legacy exec result objects, dicts, or ExecutionResult."""
        if isinstance(result, cls):
            return result
        if isinstance(result, dict):
            meta = dict(result.get("meta") or {})
            files = result.get("files_changed") or meta.get("files_changed") or []
            if isinstance(files, dict):
                files = list(files.keys())
            err = str(result.get("error") or result.get("stderr") or "")
            ok = bool(result.get("ok", result.get("success", False)))
            timed_out = bool(result.get("timed_out") or meta.get("timed_out"))
            if timed_out:
                ok = False
                if not err:
                    err = "timeout"
            return cls(
                ok=ok,
                stdout=str(result.get("stdout") or result.get("output") or "")[-8000:],
                stderr=str(result.get("stderr") or "")[-4000:],
                latency=float(result.get("latency") or result.get("duration") or 0.0),
                tokens=int(result.get("tokens") or 0),
                error=err[:2000],
                files_changed=[str(f) for f in (files or [])],
                patch=str(result.get("patch") or meta.get("patch") or "")[:4000],
                worker=str(result.get("worker") or meta.get("worker") or ""),
                timed_out=timed_out,
                exit_code=result.get("exit_code") if result.get("exit_code") is not None else result.get("code"),
                meta=meta,
            )
        meta = dict(getattr(result, "meta", None) or {})
        files = list(getattr(result, "files_changed", None) or meta.get("files_changed") or [])
        if isinstance(files, dict):
            files = list(files.keys())
        timed_out = bool(getattr(result, "timed_out", False) or meta.get("timed_out"))
        ok = bool(getattr(result, "ok", False))
        if timed_out:
            ok = False
        err = str(getattr(result, "error", "") or getattr(result, "stderr", "") or "")
        if timed_out and not err:
            err = "timeout"
        code = getattr(result, "code", None)
        if code is None:
            code = getattr(result, "exit_code", None)
        return cls(
            ok=ok,
            stdout=str(getattr(result, "stdout", "") or "")[-8000:],
            stderr=str(getattr(result, "stderr", "") or "")[-4000:],
            latency=float(getattr(result, "latency", 0.0) or getattr(result, "duration", 0.0) or 0.0),
            tokens=int(getattr(result, "tokens", 0) or 0),
            error=err[:2000],
            files_changed=[str(f) for f in files],
            patch=str(getattr(result, "patch", "") or meta.get("patch") or "")[:4000],
            worker=str(getattr(result, "worker", "") or meta.get("worker") or ""),
            timed_out=timed_out,
            exit_code=code if code is None or isinstance(code, int) else None,
            meta=meta,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stdout": self.stdout[-4000:],
            "stderr": self.stderr[-2000:],
            "latency": round(float(self.latency or 0.0), 3),
            "duration": round(float(self.latency or 0.0), 3),
            "tokens": self.tokens,
            "error": self.error,
            "files_changed": list(self.files_changed),
            "patch": (self.patch or "")[:2000],
            "worker": self.worker,
            "timed_out": bool(self.timed_out),
            "exit_code": self.exit_code,
            "meta": dict(self.meta),
        }

    def to_task_result_fields(self) -> dict[str, Any]:
        """Fields expected by build_task_result / history (product shape)."""
        d = self.to_dict()
        # Keep stderr only as error source when ok is False
        if self.ok:
            d.pop("stderr", None)
        return d


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
            return WorkerResult(ok=False, error="no exec_fn bound", worker=self.name)
        raw = self.exec_fn(self.worker, task, context)
        wr = WorkerResult.from_exec(raw)
        if not wr.worker:
            wr.worker = self.name
        return wr


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
