# -*- coding: utf-8 -*-
"""DEV-002 Recovery policies — map failure kinds → RecoveryDecision.

Does not execute workers or enqueue tasks. Runtime applies the decision.
"""
from __future__ import annotations

from typing import Any

# kind from worker_failure_contract / evidence → default action
POLICY_TABLE: dict[str, dict[str, Any]] = {
    "worker_timeout": {
        "action": "retry",
        "recoverable": True,
        "reason": "timeout",
        "prefer_local": True,
    },
    "worker_crash": {
        "action": "retry",
        "recoverable": True,
        "reason": "worker_crash",
    },
    "worker_unavailable": {
        "action": "retry",
        "recoverable": True,
        "reason": "provider_unavailable",
        "prefer_local": True,
        "allow_fallback": True,
    },
    "worker_rate_limit": {
        "action": "retry",
        "recoverable": True,
        "reason": "rate_limit",
        "prefer_local": True,
        "allow_fallback": True,
    },
    "worker_billing": {
        "action": "retry",
        "recoverable": True,
        "reason": "billing",
        "prefer_local": True,
        "allow_fallback": True,
    },
    "worker_auth": {
        "action": "ask_user",
        "recoverable": False,
        "reason": "auth_failed",
    },
    "worker_network": {
        "action": "retry",
        "recoverable": True,
        "reason": "network",
        "prefer_local": True,
        "allow_fallback": True,
    },
    "worker_model": {
        "action": "replan",
        "recoverable": True,
        "reason": "model_invalid",
    },
    "worker_loop": {
        "action": "replan",
        "recoverable": True,
        "reason": "worker_loop",
    },
    "verification_failed": {
        "action": "replan",
        "recoverable": True,
        "reason": "verification_failed",
        "allow_fallback": False,  # same worker+prompt rarely helps
    },
    "invalid_output": {
        "action": "replan",
        "recoverable": True,
        "reason": "invalid_output",
        "allow_fallback": False,
    },
    "security_violation": {
        "action": "stop",
        "recoverable": False,
        "reason": "security_violation",
    },
    "exhausted": {
        "action": "ask_user",
        "recoverable": False,
        "reason": "max_attempts_exhausted",
    },
    "reclaim_no_heartbeat": {
        "action": "retry",
        "recoverable": True,
        "reason": "reclaim_no_heartbeat",
    },
    "reclaim_max_attempts": {
        "action": "ask_user",
        "recoverable": False,
        "reason": "max_attempts_exhausted",
    },
}


def normalize_failure_kind(
    *,
    kind: str = "",
    failure_layer: str = "",
    error: str = "",
    timed_out: bool = False,
    worker_outcome: dict[str, Any] | None = None,
) -> str:
    """Unify worker_outcome.kind / failure_layer / heuristics → policy key."""
    wo = dict(worker_outcome or {})
    k = str(kind or wo.get("kind") or "").strip()
    if k in POLICY_TABLE:
        return k
    layer = str(failure_layer or "").strip()
    layer_map = {
        "verification": "verification_failed",
        "worker_infra": "worker_unavailable",
        "worker_exec": "worker_crash",
        "reclaim_no_heartbeat": "reclaim_no_heartbeat",
        "reclaim_max_attempts": "reclaim_max_attempts",
    }
    if layer in layer_map:
        return layer_map[layer]
    if timed_out or wo.get("event") == "TIMEOUT":
        return "worker_timeout"
    err = str(error or "").lower()
    if "invalid" in err and "output" in err:
        return "invalid_output"
    if any(x in err for x in ("security", "sandbox", "policy violation")):
        return "security_violation"
    if any(x in err for x in ("connection refused", "unavailable", "not found", "no such file")):
        return "worker_unavailable"
    if "429" in err or "rate limit" in err:
        return "worker_rate_limit"
    if "timeout" in err or "timed out" in err:
        return "worker_timeout"
    if "verify" in err or "pytest" in err or "syntax" in err:
        return "verification_failed"
    return k or "worker_crash"


def apply_policy(
    kind: str,
    *,
    attempts: int = 0,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Return RecoveryDecision fields for a failure kind."""
    att = int(attempts or 0)
    max_a = max(1, int(max_attempts or 3))
    if att >= max_a:
        base = dict(POLICY_TABLE["exhausted"])
        base["failure_kind"] = kind or "exhausted"
        base["attempts"] = att
        base["max_attempts"] = max_a
        base["next_attempt"] = None
        return base

    pol = dict(POLICY_TABLE.get(kind) or {
        "action": "retry",
        "recoverable": True,
        "reason": "generic",
    })
    action = str(pol.get("action") or "retry")
    # last attempt: escalate ask_user for retry/replan
    if att + 1 >= max_a and action in ("retry", "replan"):
        pol = dict(pol)
        pol["action"] = "ask_user"
        pol["recoverable"] = False
        pol["reason"] = str(pol.get("reason") or "") + "_last_attempt"
        pol["next_attempt"] = None
    else:
        pol["next_attempt"] = att + 1 if action == "retry" else None
    pol["failure_kind"] = kind
    pol["attempts"] = att
    pol["max_attempts"] = max_a
    pol.setdefault("allow_fallback", False)
    pol.setdefault("prefer_local", False)
    return pol


def decide_with_policy(
    *,
    kind: str = "",
    failure_layer: str = "",
    error: str = "",
    timed_out: bool = False,
    worker_outcome: dict[str, Any] | None = None,
    attempts: int = 0,
    max_attempts: int = 3,
    verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full policy decision used by Recovery Controller."""
    if verification and (
        verification.get("ok") is False or verification.get("passed") is False
    ):
        kind = kind or "verification_failed"
    nk = normalize_failure_kind(
        kind=kind,
        failure_layer=failure_layer,
        error=error,
        timed_out=timed_out,
        worker_outcome=worker_outcome,
    )
    decision = apply_policy(nk, attempts=attempts, max_attempts=max_attempts)
    decision["action"] = str(decision.get("action") or "stop")
    decision["suggest"] = {
        "retry": "Повторить через существующий reclaim/retry path.",
        "replan": "Новый шаг плана без обхода intake.",
        "ask_user": "Нужно решение пользователя.",
        "stop": "Авто-восстановление остановлено.",
    }.get(decision["action"], "")
    return decision
