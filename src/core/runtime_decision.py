# -*- coding: utf-8 -*-
"""DEV-001: Execution Evidence → Runtime Decision.

Single decision function for terminal state:

  ExecutionResult / Evidence + Verification → DONE | ERROR | RETRY

Worker cannot force DONE. Contradictory evidence is fail-closed.
"""
from __future__ import annotations

from typing import Any


def _ver_ok(verification: dict[str, Any] | None) -> bool | None:
    """True/False if known, None if missing."""
    if not isinstance(verification, dict) or not verification:
        return None
    if "ok" in verification:
        return bool(verification.get("ok"))
    if "passed" in verification:
        return bool(verification.get("passed"))
    r = str(verification.get("result") or verification.get("status") or "").lower()
    if r in ("pass", "passed", "ok", "success"):
        return True
    if r in ("fail", "failed", "error"):
        return False
    return None


def evidence_snapshot(
    *,
    task_id: str = "",
    worker: str = "",
    model: str = "",
    attempt: int = 0,
    exit_code: int | None = None,
    exec_ok: bool | None = None,
    timed_out: bool = False,
    changed_files: list[str] | None = None,
    stdout_summary: str = "",
    stderr_summary: str = "",
    error: str = "",
    verification: dict[str, Any] | None = None,
    failure_layer: str = "",
    plan_step: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical evidence fields used for decisions (may attach to metadata)."""
    snap: dict[str, Any] = {
        "task_id": str(task_id or ""),
        "worker": str(worker or ""),
        "model": str(model or ""),
        "attempt": int(attempt or 0),
        "plan_step": str(plan_step or ""),
        "exit_code": exit_code,
        "exec_ok": exec_ok,
        "timed_out": bool(timed_out),
        "changed_files": [str(x) for x in (changed_files or [])][:50],
        "stdout_summary": str(stdout_summary or "")[:500],
        "stderr_summary": str(stderr_summary or "")[:500],
        "error": str(error or "")[:2000],
        "verification": dict(verification or {}),
        "failure_layer": str(failure_layer or ""),
    }
    if extra:
        for k, v in extra.items():
            if k not in snap:
                snap[k] = v
    return snap


def detect_contradictions(evidence: dict[str, Any] | None) -> list[str]:
    """Return list of contradiction codes (empty = consistent)."""
    ev = dict(evidence or {})
    issues: list[str] = []
    term = str(ev.get("terminal_state") or "").upper()
    exec_ok = ev.get("exec_ok")
    ver = _ver_ok(ev.get("verification") if isinstance(ev.get("verification"), dict) else None)
    timed_out = bool(ev.get("timed_out"))
    exit_code = ev.get("exit_code")

    if term == "DONE" and exec_ok is False:
        issues.append("done_but_exec_failed")
    if term == "DONE" and timed_out:
        issues.append("done_but_timed_out")
    if term == "DONE" and ver is False:
        issues.append("done_but_verification_failed")
    if term == "DONE" and ver is None and not ev.get("short_circuit"):
        issues.append("done_without_verification")
    if exec_ok is True and timed_out:
        issues.append("exec_ok_but_timed_out")
    if exec_ok is True and exit_code not in (None, 0):
        issues.append("exec_ok_but_nonzero_exit")
    if ver is True and term == "ERROR" and not ev.get("error") and exec_ok is True:
        # soft: allowed if other reasons; not hard contradiction
        pass
    if ev.get("worker_declared_done") and ver is not True:
        issues.append("worker_self_done_without_verify")
    return issues


def decide_terminal(
    evidence: dict[str, Any] | None,
    *,
    verification_report: Any = None,
    short_circuit: str | None = None,
    allow_retry: bool = False,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Decide DONE / ERROR / RETRY from evidence (+ optional VerificationReport).

    Returns:
      {
        terminal_state, ok, reason, contradictions,
        gate_ok, evidence (normalized)
      }
    """
    ev = dict(evidence or {})
    attempt = int(ev.get("attempt") or 0)
    contradictions = detect_contradictions(ev)

    # Merge verification from report object if provided
    report = verification_report
    ver_dict = ev.get("verification") if isinstance(ev.get("verification"), dict) else {}
    if report is not None:
        try:
            if hasattr(report, "to_dict"):
                ver_dict = {**ver_dict, **report.to_dict()}
            elif isinstance(report, dict):
                ver_dict = {**ver_dict, **report}
            ev["verification"] = ver_dict
        except Exception:
            pass

    # Recompute contradictions after merge
    if report is not None:
        contradictions = detect_contradictions(ev)

    execution_ok = bool(ev.get("exec_ok"))
    if ev.get("timed_out"):
        execution_ok = False
    if ev.get("exit_code") not in (None, 0) and ev.get("exec_ok") is not True:
        execution_ok = False

    # Prefer verification_engine.gate_done when available
    gate_ok = False
    gate_reason = "not_evaluated"
    try:
        from core.verification_engine import gate_done, report_from_dict

        rep = report
        if rep is None and ver_dict:
            rep = report_from_dict(ver_dict)
        gate_ok, gate_reason = gate_done(
            execution_ok, rep, short_circuit=short_circuit or ev.get("short_circuit")
        )
    except Exception:
        # Local fail-closed mirror of gate_done
        if short_circuit in ("cache_hit", "skill_success") and _ver_ok(ver_dict) is not False:
            gate_ok, gate_reason = True, f"short_circuit:{short_circuit}"
        elif not execution_ok:
            gate_ok, gate_reason = False, "execution_failed"
        elif _ver_ok(ver_dict) is None:
            gate_ok, gate_reason = False, "verification_missing"
        elif _ver_ok(ver_dict) is False:
            gate_ok, gate_reason = False, "verification_failed"
        else:
            gate_ok, gate_reason = True, "ok"

    if contradictions:
        gate_ok = False
        gate_reason = "contradictory_evidence:" + ",".join(contradictions)

    if gate_ok:
        terminal = "DONE"
        reason = gate_reason
    else:
        # RETRY only when allowed and recoverable-ish
        recoverable = gate_reason in (
            "execution_failed",
            "verification_failed",
            "verification_missing",
        ) or any(
            c in ("done_but_verification_failed", "done_without_verification")
            for c in contradictions
        )
        if allow_retry and recoverable and attempt + 1 < max(1, int(max_attempts or 3)):
            terminal = "RETRY"
            reason = gate_reason
        else:
            terminal = "ERROR"
            reason = gate_reason

    ev["terminal_state"] = terminal
    return {
        "terminal_state": terminal,
        "ok": terminal == "DONE",
        "reason": reason,
        "gate_ok": gate_ok,
        "contradictions": contradictions,
        "evidence": ev,
        "allow_retry": allow_retry,
    }


def decide_from_task_payload(
    payload: dict[str, Any] | None,
    *,
    allow_retry: bool = False,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Extract evidence from task JSON / finish_task result and decide."""
    raw = dict(payload or {})
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    res = raw.get("result") if isinstance(raw.get("result"), dict) else {}
    ev = meta.get("execution_evidence") if isinstance(meta.get("execution_evidence"), dict) else {}
    if not ev:
        ev = evidence_snapshot(
            task_id=str(raw.get("id") or ""),
            worker=str(res.get("worker") or meta.get("worker") or ""),
            model=str(res.get("model") or meta.get("model") or ""),
            attempt=int(raw.get("attempts") or meta.get("attempts") or 0),
            exit_code=res.get("exit_code") if "exit_code" in res else res.get("code"),
            exec_ok=res.get("ok") if "ok" in res else None,
            timed_out=bool(res.get("timed_out")),
            changed_files=list(res.get("changed_files") or meta.get("changed_files") or []),
            stdout_summary=str(res.get("stdout") or "")[-500:],
            stderr_summary=str(res.get("stderr") or "")[-500:],
            error=str(res.get("error") or raw.get("error") or ""),
            verification=res.get("verification") if isinstance(res.get("verification"), dict) else meta.get("verification"),
            failure_layer=str(meta.get("failure_layer") or ""),
            plan_step=str(meta.get("plan_step_id") or ""),
        )
    # claimed terminal from payload is not trusted
    ev.pop("terminal_state", None)
    if res.get("verified") is True or res.get("verify_ok") is True:
        ver = dict(ev.get("verification") or {})
        ver.setdefault("ok", True)
        ev["verification"] = ver
    return decide_terminal(ev, allow_retry=allow_retry, max_attempts=max_attempts)
