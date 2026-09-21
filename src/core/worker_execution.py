# -*- coding: utf-8 -*-
"""WorkerExecution contract — normalize worker output for Runtime.

Runtime depends on this shape, not on Aider/Ollama internals.
Does not select workers or change FSM.
"""
from __future__ import annotations

from typing import Any


def normalize_execution_result(
    *,
    ok: bool,
    worker: str = "",
    model: str = "",
    stdout: str = "",
    stderr: str = "",
    error: str = "",
    timed_out: bool = False,
    latency_sec: float = 0.0,
    changed_files: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical ExecutionResult dict."""
    err = str(error or "").strip()
    if not err and not ok:
        err = str(stderr or "")[:500] or "worker_failed"
    return {
        "ok": bool(ok),
        "worker": str(worker or ""),
        "model": str(model or ""),
        "stdout": str(stdout or "")[:50000],
        "stderr": str(stderr or "")[:20000],
        "error": err[:2000],
        "timed_out": bool(timed_out),
        "latency_sec": float(latency_sec or 0.0),
        "changed_files": [str(x) for x in (changed_files or [])][:50],
        "extra": dict(extra or {}),
    }


def from_worker_result_object(result: Any, *, worker: str = "", model: str = "") -> dict[str, Any]:
    """Adapt typical executor result object → ExecutionResult."""
    if result is None:
        return normalize_execution_result(ok=False, worker=worker, model=model, error="no_result")
    if isinstance(result, dict):
        return normalize_execution_result(
            ok=bool(result.get("ok")),
            worker=str(result.get("worker") or worker),
            model=str(result.get("model") or model),
            stdout=str(result.get("stdout") or ""),
            stderr=str(result.get("stderr") or ""),
            error=str(result.get("error") or ""),
            timed_out=bool(result.get("timed_out")),
            latency_sec=float(result.get("latency") or result.get("latency_sec") or 0),
            changed_files=list(result.get("changed_files") or []),
            extra={k: v for k, v in result.items() if k not in (
                "ok", "worker", "model", "stdout", "stderr", "error", "timed_out",
                "latency", "latency_sec", "changed_files"
            )},
        )
    return normalize_execution_result(
        ok=bool(getattr(result, "ok", False)),
        worker=worker or str(getattr(result, "worker", "") or ""),
        model=model or str(getattr(result, "model", "") or ""),
        stdout=str(getattr(result, "stdout", "") or ""),
        stderr=str(getattr(result, "stderr", "") or ""),
        error=str(getattr(result, "error", "") or ""),
        timed_out=bool(getattr(result, "timed_out", False)),
        latency_sec=float(getattr(result, "latency", 0) or 0),
        changed_files=list(getattr(result, "changed_files", None) or []),
    )


def route_decision_record(
    *,
    worker: str,
    reason: str = "",
    advisory: bool = True,
    model: str = "",
    score: float | None = None,
) -> dict[str, Any]:
    """RouteDecision surface record (does not call select_executor)."""
    return {
        "worker": str(worker or ""),
        "model": str(model or ""),
        "reason": str(reason or ""),
        "advisory": bool(advisory),
        "score": score,
    }
