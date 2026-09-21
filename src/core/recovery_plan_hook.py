# -*- coding: utf-8 -*-
"""Plan-layer replan from ERROR recovery decision.

- Only runs when decide_recovery action == "replan"
- Uses intelligence.plan_runtime_bridge.replan_after_error
- NEVER enqueues LocalQueue / never changes Runtime FSM
"""
from __future__ import annotations

from typing import Any

from core.recovery_decision import decide_from_task_row
from core.recovery_mechanism import mechanism_for_decision


def try_plan_replan_from_error(
    row: dict[str, Any] | None,
    plan: Any = None,
    *,
    new_action: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """If recovery says replan and plan+step available → replan_after_error.

    Returns structured result; ok=False with skipped=True when not applicable.
    """
    raw = dict(row or {})
    decision = decide_from_task_row(raw)
    mech = mechanism_for_decision(decision)
    out: dict[str, Any] = {
        "ok": False,
        "decision": decision,
        "mechanism": mech,
        "enqueued": False,
    }
    if mech.get("enqueue_new"):
        # hard contract
        out["error"] = "enqueue_forbidden"
        return out

    if str(decision.get("action") or "") != "replan":
        out["skipped"] = True
        out["reason"] = "action_not_replan"
        return out

    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    step_id = str(
        meta.get("plan_step_id")
        or meta.get("step_id")
        or meta.get("living_step_id")
        or raw.get("plan_step_id")
        or ""
    ).strip()
    if not step_id:
        out["skipped"] = True
        out["reason"] = "no_plan_step_id"
        return out

    if plan is None:
        out["skipped"] = True
        out["reason"] = "no_plan_loaded"
        return out

    action = (new_action or "").strip()
    if not action:
        action = str(raw.get("message") or meta.get("message") or "retry after error").strip()

    try:
        from intelligence.plan_runtime_bridge import replan_after_error

        result = replan_after_error(
            plan,
            step_id,
            new_action=action,
            reason=reason or str(decision.get("reason") or "recovery_replan"),
        )
        out.update(result if isinstance(result, dict) else {"ok": False, "error": "bad_result"})
        out["enqueued"] = False
        out["decision"] = decision
        out["mechanism"] = mech
        return out
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out


def annotate_row_with_replan_result(
    row: dict[str, Any],
    replan_result: dict[str, Any],
) -> dict[str, Any]:
    """Attach plan replan outcome to metadata (display / evidence only)."""
    out = dict(row)
    meta = dict(out.get("metadata") if isinstance(out.get("metadata"), dict) else {})
    meta["plan_replan"] = {
        k: replan_result.get(k)
        for k in ("ok", "new_step_id", "error_step_id", "version", "error", "skipped", "reason")
        if k in replan_result
    }
    out["metadata"] = meta
    return out
