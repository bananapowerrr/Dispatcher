# -*- coding: utf-8 -*-
"""R3 Recovery Controller — single managed recovery path.

ERROR → classify (via recovery_decision) → mechanism → optional plan replan.

Does NOT:
  - enqueue LocalQueue / intake
  - bypass FSM or DONE gate
  - declare DONE

Does:
  - attach recovery_decision + recovery_mechanism metadata
  - plan-layer replan when action=replan and plan/step available
  - record outcome for Chat / evidence
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from core.recovery_decision import decide_from_task_row
from core.recovery_mechanism import assert_no_enqueue, mechanism_for_decision


def run_recovery(
    row: dict[str, Any] | None,
    *,
    plan: Any = None,
    project_root: str | Path | None = None,
    apply_plan: bool = True,
    save_plan: bool = True,
) -> dict[str, Any]:
    """Execute recovery controller for an ERROR (or reclaim) task row.

    Returns outcome dict; always enqueued=False.
    """
    raw = dict(row or {})
    decision = decide_from_task_row(raw)
    mechanism = mechanism_for_decision(decision)
    out: dict[str, Any] = {
        "ok": True,
        "enqueued": False,
        "decision": decision,
        "mechanism": mechanism,
        "plan_replan": None,
        "applied": False,
        "chat_extra": "",
    }

    if not assert_no_enqueue(mechanism):
        out["ok"] = False
        out["error"] = "enqueue_forbidden"
        return out

    action = str(decision.get("action") or "stop")
    suggest = str(decision.get("suggest") or "")
    layer = str(decision.get("failure_layer") or "")

    if action == "retry":
        out["chat_extra"] = f"→ Recovery: retry [{layer}] — {suggest}".strip(" —")
        out["applied"] = False  # Runtime reclaim/retry states apply elsewhere
        out["hint"] = "existing_reclaim_or_retry_states"
        return out

    if action in ("ask_user", "stop"):
        out["chat_extra"] = f"→ Recovery: {action} [{layer}] — {suggest}".strip(" —")
        out["applied"] = False
        out["hint"] = "ui_only" if action == "ask_user" else "none"
        return out

    if action != "replan":
        out["chat_extra"] = f"→ Recovery: {action}"
        return out

    # --- plan-layer replan only ---
    if not apply_plan:
        out["chat_extra"] = f"→ Recovery: replan (deferred) [{layer}]"
        out["hint"] = "plan_layer_only"
        return out

    loaded = plan
    root = Path(project_root) if project_root else None
    if loaded is None and root is not None:
        try:
            from intelligence.living_plan import load_living_plan

            loaded = load_living_plan(root)
        except Exception as exc:
            out["plan_replan"] = {
                "ok": False,
                "skipped": True,
                "reason": f"plan_load:{type(exc).__name__}",
            }
            out["chat_extra"] = f"→ replan skipped (plan load: {type(exc).__name__})"
            return out

    from core.recovery_plan_hook import try_plan_replan_from_error

    replan = try_plan_replan_from_error(raw, loaded)
    out["plan_replan"] = replan
    out["enqueued"] = False

    if replan.get("ok"):
        out["applied"] = True
        out["hint"] = "plan_layer_only"
        if save_plan and root is not None and loaded is not None:
            try:
                from intelligence.living_plan import save_living_plan

                save_living_plan(root, loaded)
            except Exception as exc:
                out["save_error"] = str(exc)[:200]
        eid = replan.get("error_step_id")
        nid = replan.get("new_step_id")
        out["chat_extra"] = f"→ Plan replan: {eid} ERROR kept · added `{nid}` PENDING"
    elif replan.get("skipped"):
        out["chat_extra"] = f"→ replan skipped: {replan.get('reason')}"
    else:
        out["chat_extra"] = f"→ replan failed: {replan.get('error') or 'unknown'}"
        out["ok"] = False

    return out


def annotate_row_with_recovery(
    row: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Attach controller outcome under metadata (evidence / Chat)."""
    out = dict(row)
    meta = dict(out.get("metadata") if isinstance(out.get("metadata"), dict) else {})
    meta["recovery_decision"] = outcome.get("decision") or meta.get("recovery_decision")
    meta["recovery_mechanism"] = (
        (outcome.get("mechanism") or {}).get("path")
        or meta.get("recovery_mechanism")
    )
    meta["recovery_controller"] = {
        "applied": outcome.get("applied"),
        "enqueued": False,
        "hint": outcome.get("hint"),
        "plan_replan": outcome.get("plan_replan"),
        "chat_extra": outcome.get("chat_extra"),
    }
    out["metadata"] = meta
    return out
