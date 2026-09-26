# -*- coding: utf-8 -*-
"""Recovery decision (advisory) — does NOT enqueue or change FSM.

Given ERROR evidence / failure_layer → recommend: retry | replan | ask_user | stop.
"""
from __future__ import annotations

from typing import Any

from core.execution_evidence import classify_failure_layer


def decide_recovery(
    *,
    error: str = "",
    reclaim_reason: str = "",
    verification: dict[str, Any] | None = None,
    attempts: int = 0,
    max_attempts: int = 3,
    failure_layer: str = "",
    recoverable: bool | None = None,
) -> dict[str, Any]:
    """Return structured recovery decision for UI / planner.

    Actions:
      retry     — same plan step, Runtime may reclaim/requeue
      replan    — planner should add retry step (plan layer)
      ask_user  — needs human choice
      stop      — no automatic recovery
    """
    att = int(attempts or 0)
    max_a = max(1, int(max_attempts or 3))
    # DEV-002: policy table first
    try:
        from core.recovery_policy import decide_with_policy

        pol = decide_with_policy(
            failure_layer=failure_layer,
            error=error or reclaim_reason,
            timed_out="timeout" in str(error or "").lower() or "timeout" in str(reclaim_reason or "").lower(),
            attempts=att,
            max_attempts=max_a,
            verification=verification,
        )
        return {
            "action": pol.get("action") or "stop",
            "recoverable": bool(pol.get("recoverable")),
            "failure_layer": failure_layer or pol.get("failure_kind") or "",
            "failure_kind": pol.get("failure_kind") or "",
            "reason": pol.get("reason") or "",
            "suggest": pol.get("suggest") or "",
            "next_attempt": pol.get("next_attempt"),
            "allow_fallback": bool(pol.get("allow_fallback")),
            "prefer_local": bool(pol.get("prefer_local")),
            "attempts": att,
            "max_attempts": max_a,
        }
    except Exception:
        pass

    layer = failure_layer
    rec = recoverable
    if not layer:
        layer, rec_guess = classify_failure_layer(
            error=error, reclaim_reason=reclaim_reason, verification=verification
        )
        if rec is None:
            rec = rec_guess
    if rec is None:
        rec = True

    if layer == "reclaim_max_attempts" or att >= max_a:
        return {
            "action": "ask_user",
            "recoverable": False,
            "failure_layer": layer or "reclaim_max_attempts",
            "reason": "max_attempts_exhausted",
            "suggest": "Проверьте worker/логи или уменьшите задачу.",
        }

    if layer == "verification":
        return {
            "action": "replan" if att + 1 < max_a else "ask_user",
            "recoverable": att + 1 < max_a,
            "failure_layer": "verification",
            "reason": "verification_failed",
            "suggest": "Повторить с уточнённым шагом или поправить verify.",
        }

    if layer in ("worker_infra", "reclaim_no_heartbeat"):
        return {
            "action": "retry",
            "recoverable": True,
            "failure_layer": layer,
            "reason": "transient_infra",
            "suggest": "Повторить после проверки Ollama/Aider/lease.",
        }

    if layer == "worker_exec":
        return {
            "action": "replan" if att + 1 < max_a else "ask_user",
            "recoverable": att + 1 < max_a,
            "failure_layer": layer,
            "reason": "worker_exec_failed",
            "suggest": "Другой worker или упростить задачу.",
        }

    if not rec:
        return {
            "action": "stop",
            "recoverable": False,
            "failure_layer": layer or "unknown",
            "reason": "not_recoverable",
            "suggest": "Нужно вмешательство пользователя.",
        }

    return {
        "action": "retry" if att + 1 < max_a else "ask_user",
        "recoverable": att + 1 < max_a,
        "failure_layer": layer or "unknown",
        "reason": "generic",
        "suggest": "Повтор или решение пользователя.",
    }


def decide_from_task_row(row: dict[str, Any] | None) -> dict[str, Any]:
    """Extract fields from task JSON / ERROR row."""
    raw = dict(row or {})
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    res = raw.get("result") if isinstance(raw.get("result"), dict) else {}
    ev = meta.get("execution_evidence") if isinstance(meta.get("execution_evidence"), dict) else {}
    err = str(res.get("error") or raw.get("error") or ev.get("error") or "")
    wo = meta.get("worker_outcome") if isinstance(meta.get("worker_outcome"), dict) else {}
    # Route everything through decide_recovery: it consults the DEV-002 policy
    # first and always returns the normalized shape (incl. failure_layer).
    return decide_recovery(
        error=err,
        reclaim_reason=str(meta.get("reclaim_reason") or ""),
        verification=res.get("verification") if isinstance(res.get("verification"), dict) else ev.get("verification"),
        attempts=int(raw.get("attempts") or meta.get("attempts") or ev.get("attempt") or 0),
        max_attempts=int(meta.get("max_attempts") or 3),
        failure_layer=str(meta.get("failure_layer") or ""),
        recoverable=meta.get("recoverable") if "recoverable" in meta else None,
    )
