# -*- coding: utf-8 -*-
"""NIGHT-RT-001: Night execute_fn adapters for Runtime.

Night loop calls execute_fn(payload) → terminal dict.
This module provides:

  mock_execute_fn          — offline tests (no Ollama/Aider)
  runtime_execute_fn(rt)   — wraps Runtime.process without FSM bypass
  make_execute_fn(...)     — factory

Does not enqueue LocalQueue itself; Runtime.process owns claim/verify/DONE gate.
"""
from __future__ import annotations

from typing import Any, Callable


def _normalize_terminal(status: str | None, *, error: str = "", verified: bool | None = None) -> dict[str, Any]:
    st = str(status or "ERROR").upper()
    if st in ("DONE", "ERROR", "DEFERRED", "DEDUPED", "RETRY"):
        terminal = st if st != "DEDUPED" else "DEFERRED"
    else:
        terminal = "ERROR"
        error = error or f"unknown_status:{status}"
    out: dict[str, Any] = {
        "terminal_state": terminal,
        "status": terminal,
        "error": error,
        "result": {},
    }
    if verified is not None:
        out["verified"] = bool(verified)
    elif terminal == "DONE":
        # Runtime.process only returns DONE after verify gate — trust unless contradicted
        out["verified"] = True
        out["gate_ok"] = True
    return out


def mock_execute_fn(
    payload: dict[str, Any],
    *,
    mode: str = "done",
) -> dict[str, Any]:
    """Deterministic offline executor for Night tests."""
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    sid = str(meta.get("plan_step_id") or payload.get("id") or "")
    if mode == "error":
        return {
            "terminal_state": "ERROR",
            "error": "mock_error",
            "verified": False,
            "worker_result": {"kind": "worker_crash", "status": "failure"},
            "attempts": 0,
            "result": {"error": "mock_error"},
        }
    if mode == "timeout":
        return {
            "terminal_state": "ERROR",
            "error": "timeout",
            "timed_out": True,
            "verified": False,
            "worker_result": {"kind": "worker_timeout", "status": "timeout"},
            "attempts": 0,
        }
    if mode == "unverified_done":
        return {"terminal_state": "DONE", "verified": False, "error": "would_be_false_done"}
    return {
        "terminal_state": "DONE",
        "verified": True,
        "gate_ok": True,
        "result": {"ok": True, "plan_step_id": sid},
    }


def runtime_execute_fn(
    runtime: Any,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Bind a Runtime instance → execute_fn for run_autonomous_loop.

    Uses Runtime.process(raw). Does not open a second parallel project lock
    beyond what Runtime already enforces (MAX_PARALLEL_PROJECTS=1 at night layer).
    """

    def _exec(payload: dict[str, Any]) -> dict[str, Any]:
        raw = dict(payload or {})
        meta = dict(raw.get("metadata") or {})
        meta.setdefault("source", "night_runtime_bridge")
        meta.setdefault("night_mode", True)
        raw["metadata"] = meta
        if not raw.get("id"):
            import uuid
            raw["id"] = f"night-{uuid.uuid4().hex[:12]}"
        try:
            status = runtime.process(raw)
        except Exception as exc:
            return {
                "terminal_state": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
                "verified": False,
                "result": {},
                "attempts": int(raw.get("attempts") or 0),
            }
        # Best-effort: read back task row if Runtime exposes _load / bus
        verified = None
        error = ""
        result: dict[str, Any] = {}
        worker_result = None
        try:
            tid = str(raw.get("id") or "")
            row = None
            if hasattr(runtime, "_load") and tid:
                row = runtime._load(tid)
            elif hasattr(runtime, "load_task") and tid:
                row = runtime.load_task(tid)
            if isinstance(row, dict):
                result = dict(row.get("result") or {})
                error = str(result.get("error") or row.get("error") or "")
                meta2 = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                worker_result = meta2.get("worker_result")
                if result.get("verified") is True or result.get("verify_ok") is True:
                    verified = True
                if str(row.get("status") or "").upper() == "DONE":
                    verified = True if verified is None else verified
            elif row is not None and hasattr(row, "status"):
                st = str(getattr(row, "status", "") or "").upper()
                if st == "DONE":
                    verified = True
                error = str(getattr(row, "error", "") or "")
        except Exception:
            pass
        out = _normalize_terminal(status, error=error, verified=verified)
        out["result"] = result
        out["attempts"] = int(raw.get("attempts") or 0)
        if worker_result:
            out["worker_result"] = worker_result
        return out

    return _exec


def make_execute_fn(
    *,
    runtime: Any = None,
    mock: bool = False,
    mock_mode: str = "done",
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Factory: real Runtime if given, else mock (offline-safe default)."""
    if mock or runtime is None:
        def _m(payload: dict[str, Any]) -> dict[str, Any]:
            return mock_execute_fn(payload, mode=mock_mode)
        return _m
    return runtime_execute_fn(runtime)


def try_bind_default_runtime() -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    """Optional: construct Runtime() if importable. Returns None offline without deps."""
    try:
        from core.runtime import Runtime

        rt = Runtime()
        return runtime_execute_fn(rt)
    except Exception:
        return None
