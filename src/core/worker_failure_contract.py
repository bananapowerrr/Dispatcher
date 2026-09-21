# -*- coding: utf-8 -*-
"""R4 Worker Failure / Fallback Contract.

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
        return {
            "kind": "worker_crash",
            "switch_backend": True,
            "prefer_local": False,
            "worker_ok": False,
            "verification_ok": None,
            "event": "ERROR",
            "err_type": "ERROR",
            "fail_status": "ERROR",
            "detail": "no_result",
            "fallback_kind": "other",
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
