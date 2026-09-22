# -*- coding: utf-8 -*-
"""DEV-003 / R4 Worker Failure Contract + WorkerResult.

WorkerResult.status ∈ {success, failure, timeout, unavailable, invalid_output}

Maps ExecutionResult → one outcome kind for Runtime:

  worker_ok
  worker_timeout
  worker_crash
  worker_unavailable   (preflight / no binary / no key)
  worker_rate_limit
  worker_billing
  worker_auth
  worker_network
  worker_model
  worker_loop
  verification_failed  (worker ok, code/tests failed — not a worker infra fail)

Does not change FSM. Does not declare DONE.
"""
from __future__ import annotations

from typing import Any

# Outcome → may try another worker in same task loop?
SWITCH_BACKEND = frozenset({
    "worker_timeout",
    "worker_crash",
    "worker_unavailable",
    "worker_rate_limit",
    "worker_billing",
    "worker_auth",
    "worker_network",
    "worker_model",
    "worker_loop",
})

# Prefer local backends after these
PREFER_LOCAL = frozenset({
    "worker_timeout",
    "worker_rate_limit",
    "worker_billing",
    "worker_auth",
    "worker_network",
})

# verification failure is not worker infra — do not switch for "infra" reasons alone
# (Runtime may still replan)

KIND_TO_FALLBACK = {
    "worker_timeout": "timeout",
    "worker_rate_limit": "rate_limit",
    "worker_billing": "billing",
    "worker_auth": "auth",
    "worker_network": "network",
    "worker_model": "model",
    "worker_crash": "other",
    "worker_unavailable": "other",
    "worker_loop": "other",
    "verification_failed": "other",
    "worker_ok": "other",
}


def classify_execution_outcome(
    result: Any = None,
    *,
    preflight_ok: bool | None = None,
    preflight_reason: str = "",
    verification_ok: bool | None = None,
    error_text: str = "",
) -> dict[str, Any]:
    """Single structured outcome from worker attempt (+ optional verify)."""
    # Preflight failed before run
    if preflight_ok is False:
        return {
            "kind": "worker_unavailable",
            "switch_backend": True,
            "prefer_local": True,
            "worker_ok": False,
            "verification_ok": None,
            "event": "UNAVAILABLE",
            "err_type": "UNAVAILABLE",
            "fail_status": "ERROR",
            "detail": str(preflight_reason or "preflight_failed")[:500],
            "fallback_kind": "other",
        }

    if result is None:
        detail = str(error_text or "no_result")[:500]
        # classify from error text when no ExecutionResult object
        kind = "worker_crash"
        prefer_local = False
        low = detail.lower()
        if any(x in low for x in ("timeout", "timed out", "deadline")):
            kind = "worker_timeout"
        elif any(x in low for x in ("not found", "не найден", "missing", "no such", "unavailable", "preflight")):
            kind = "worker_unavailable"
            prefer_local = True
        elif any(x in low for x in ("rate limit", "429", "quota")):
            kind = "worker_rate_limit"
            prefer_local = True
        elif any(x in low for x in ("auth", "401", "403", "api_key", "api key")):
            kind = "worker_auth"
            prefer_local = True
        return {
            "kind": kind,
            "switch_backend": True,
            "prefer_local": prefer_local,
            "worker_ok": False,
            "verification_ok": None,
            "event": "ERROR",
            "err_type": "ERROR",
            "fail_status": "ERROR",
            "detail": detail or "no_result",
            "fallback_kind": KIND_TO_FALLBACK.get(kind, "other"),
        }

    timed_out = bool(getattr(result, "timed_out", False) if not isinstance(result, dict)
                     else result.get("timed_out"))
    ok = bool(getattr(result, "ok", False) if not isinstance(result, dict)
              else result.get("ok"))
    loop = bool(getattr(result, "loop_error", False) if not isinstance(result, dict)
                else result.get("loop_error"))
    rate = bool(getattr(result, "rate_limit_error", False) if not isinstance(result, dict)
                else result.get("rate_limit_error"))
    bill = bool(getattr(result, "billing_error", False) if not isinstance(result, dict)
                else result.get("billing_error"))
    err = error_text or (
        str(getattr(result, "error", "") or getattr(result, "stderr", "") or "")
        if not isinstance(result, dict)
        else str(result.get("error") or result.get("stderr") or "")
    )

    # Refine via fallback.classify_failure text
    try:
        from core.fallback import classify_failure
        fb = classify_failure(err, timed_out=timed_out)
    except Exception:
        fb = "timeout" if timed_out else "other"

    kind = "worker_ok"
    event = "OK"
    err_type = "OK"
    fail_status = "OK"

    if timed_out or fb == "timeout":
        kind, event, err_type, fail_status = "worker_timeout", "TIMEOUT", "TIMEOUT", "ERROR"
    elif loop:
        kind, event, err_type, fail_status = "worker_loop", "LOOP", "LOOP", "LOOP"
    elif rate or fb == "rate_limit":
        kind, event, err_type, fail_status = "worker_rate_limit", "RATE_LIMIT", "RATE_LIMIT", "ERROR"
    elif bill or fb == "billing":
        kind, event, err_type, fail_status = "worker_billing", "BILLING", "BILLING", "ERROR"
    elif fb == "auth":
        kind, event, err_type, fail_status = "worker_auth", "AUTH", "AUTH", "ERROR"
    elif fb == "network":
        kind, event, err_type, fail_status = "worker_network", "NETWORK", "NETWORK", "ERROR"
    elif fb == "model":
        kind, event, err_type, fail_status = "worker_model", "MODEL", "MODEL", "ERROR"
    elif not ok:
        kind, event, err_type, fail_status = "worker_crash", "ERROR", "ERROR", "ERROR"
    else:
        kind, event, err_type, fail_status = "worker_ok", "OK", "OK", "OK"

    # Worker succeeded but verification failed — distinct from infra
    if kind == "worker_ok" and verification_ok is False:
        kind = "verification_failed"
        event = "VERIFY_FAIL"
        err_type = "VERIFY_FAIL"
        fail_status = "ERROR"

    return {
        "kind": kind,
        "switch_backend": kind in SWITCH_BACKEND,
        "prefer_local": kind in PREFER_LOCAL,
        "worker_ok": kind == "worker_ok",
        "verification_ok": verification_ok,
        "event": event,
        "err_type": err_type,
        "fail_status": fail_status,
        "detail": err[:500],
        "fallback_kind": KIND_TO_FALLBACK.get(kind, "other"),
    }


def outcome_from_preflight(ok: bool, reason: str = "") -> dict[str, Any]:
    return classify_execution_outcome(None, preflight_ok=ok, preflight_reason=reason)


# --- DEV-003 WorkerResult (runtime-facing) ---

WORKER_RESULT_STATUS = frozenset({
    "success",
    "failure",
    "timeout",
    "unavailable",
    "invalid_output",
})

KIND_TO_STATUS = {
    "worker_ok": "success",
    "worker_timeout": "timeout",
    "worker_unavailable": "unavailable",
    "worker_crash": "failure",
    "worker_rate_limit": "failure",
    "worker_billing": "failure",
    "worker_auth": "failure",
    "worker_network": "failure",
    "worker_model": "invalid_output",
    "worker_loop": "invalid_output",
    "verification_failed": "success",  # worker ran; verify is separate layer
}


def to_worker_result(
    result: Any = None,
    *,
    preflight_ok: bool | None = None,
    preflight_reason: str = "",
    verification_ok: bool | None = None,
    error_text: str = "",
    worker: str = "",
    model: str = "",
) -> dict[str, Any]:
    """Canonical WorkerResult for Runtime (not DONE — verification is separate).

    status:
      success       — process finished ok (may still fail verification later)
      failure       — crash / rate limit / network / auth / billing
      timeout       — timed out
      unavailable   — preflight / binary / key missing
      invalid_output— loop / bad model / garbage output
    """
    outcome = classify_execution_outcome(
        result,
        preflight_ok=preflight_ok,
        preflight_reason=preflight_reason,
        verification_ok=verification_ok,
        error_text=error_text,
    )
    kind = str(outcome.get("kind") or "worker_crash")
    status = KIND_TO_STATUS.get(kind, "failure")
    if kind == "worker_ok" and verification_ok is False:
        # still success at worker layer
        status = "success"

    exit_code = None
    latency = 0.0
    stdout = stderr = error = ""
    if result is not None:
        if isinstance(result, dict):
            exit_code = result.get("code", result.get("exit_code"))
            latency = float(result.get("latency") or result.get("latency_sec") or 0)
            stdout = str(result.get("stdout") or "")
            stderr = str(result.get("stderr") or "")
            error = str(result.get("error") or "")
        else:
            exit_code = getattr(result, "code", None)
            latency = float(getattr(result, "latency", 0) or 0)
            stdout = str(getattr(result, "stdout", "") or "")
            stderr = str(getattr(result, "stderr", "") or "")
            error = str(getattr(result, "error", "") or "")

    return {
        "status": status,
        "kind": kind,
        "ok": status == "success",
        "worker": str(worker or ""),
        "model": str(model or ""),
        "exit_code": exit_code,
        "timed_out": status == "timeout",
        "latency_sec": latency,
        "stdout_summary": stdout[-500:],
        "stderr_summary": stderr[-500:],
        "error": (error or str(outcome.get("detail") or ""))[:2000],
        "switch_backend": bool(outcome.get("switch_backend")),
        "prefer_local": bool(outcome.get("prefer_local")),
        "fallback_kind": outcome.get("fallback_kind") or "other",
        "event": outcome.get("event") or "",
        "verification_ok": verification_ok,
        # never a terminal DONE claim
        "terminal_state": None,
    }


def worker_result_from_execution_result(
    result: Any,
    *,
    worker: str = "",
    model: str = "",
) -> dict[str, Any]:
    """Adapter: executor.ExecutionResult → WorkerResult."""
    return to_worker_result(result, worker=worker, model=model)
