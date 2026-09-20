# -*- coding: utf-8 -*-
"""Day-2: Plan ↔ Task outcome bridge (no Runtime/FSM mutation).

Maps terminal task results onto LivingPlan steps and decides which steps
may enter the queue next. Does not enqueue tasks and does not touch DONE gate.
"""
from __future__ import annotations

from typing import Any

from intelligence.living_plan import (
    LivingPlan,
    LivingStep,
    is_active,
    is_finished,
    normalize_status,
)


_TASK_TO_STEP = {
    "DONE": "DONE",
    "SUCCESS": "DONE",
    "ERROR": "ERROR",
    "FAILED": "ERROR",
    "FAIL": "ERROR",
    "CANCELLED": "CANCELLED",
    "CANCELED": "CANCELLED",
    "RETRY": "IN_PROGRESS",  # still open from plan POV until terminal
    "PROCESSING": "IN_PROGRESS",
    "CLAIMED": "IN_PROGRESS",
    "VERIFYING": "IN_PROGRESS",
    "PENDING": "PENDING",
}


def map_task_status_to_step(task_status: str | None) -> str:
    st = (task_status or "").strip().upper()
    return _TASK_TO_STEP.get(st, normalize_status(st) if st else "PENDING")


def apply_task_outcome(
    plan: LivingPlan,
    step_id: str,
    *,
    task_status: str,
    task_id: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Update plan step from task terminal/progress status.

    Rules:
      - DONE/ERROR freeze (living_plan.mark already protects DONE)
      - IN_PROGRESS while worker runs
      - does not supersede other steps
    """
    step = plan.get(step_id)
    if step is None:
        return {"ok": False, "error": "step_not_found", "step_id": step_id}

    new_st = map_task_status_to_step(task_status)
    old = normalize_status(step.status)

    # Terminal task ERROR after DONE is ignored
    if old == "DONE" and new_st != "DONE":
        return {
            "ok": False,
            "error": "step_frozen_done",
            "step_id": step_id,
            "status": old,
        }

    ok = plan.mark(step_id, new_st, reason=reason or f"task:{task_status}")
    if task_id:
        meta = dict(step.meta or {})
        meta["task_id"] = str(task_id)
        meta["last_task_status"] = str(task_status)
        step.meta = meta
        plan.touch()

    return {
        "ok": ok,
        "step_id": step_id,
        "old_status": old,
        "new_status": normalize_status(step.status),
        "task_id": task_id,
    }


def has_in_progress(plan: LivingPlan) -> bool:
    return any(normalize_status(s.status) == "IN_PROGRESS" for s in plan.steps)


def eligible_serial(plan: LivingPlan) -> list[LivingStep]:
    """Like eligible_for_queue, but at most one active flight.

    If any step is IN_PROGRESS, return [] so the next step does not start early.
    ERROR deps still block dependents (via eligible_for_queue).
    """
    if has_in_progress(plan):
        return []
    return list(plan.eligible_for_queue())


def next_step(plan: LivingPlan, *, serial: bool = True) -> LivingStep | None:
    steps = eligible_serial(plan) if serial else plan.eligible_for_queue()
    return steps[0] if steps else None


def replan_after_error(
    plan: LivingPlan,
    error_step_id: str,
    *,
    new_action: str,
    reason: str = "",
) -> dict[str, Any]:
    """After step ERROR: keep ERROR frozen, supersede is N/A for finished;
    add replacement step that depends on prior DONE steps only.

    ERROR steps are finished — cannot supersede them. Add a new step instead.
    """
    err = plan.get(error_step_id)
    if err is None:
        return {"ok": False, "error": "step_not_found"}

    st = normalize_status(err.status)
    if st != "ERROR":
        return {"ok": False, "error": f"expected ERROR, got {st}"}

    # New step continues work; does not rewrite ERROR history
    new_id = f"{error_step_id}_retry"
    existing = {x.id for x in plan.steps}
    n = 1
    while new_id in existing:
        new_id = f"{error_step_id}_retry_{n}"
        n += 1

    # depend on DONE siblings that error depended on
    deps = [d for d in (err.depends_on or []) if True]
    # drop dependency on the failed step itself
    deps = [d for d in deps if d != error_step_id]

    replacement = LivingStep(
        id=new_id,
        action=(new_action or err.action or "retry after error").strip(),
        target=err.target,
        note=f"retry after {error_step_id} ERROR",
        files=list(err.files),
        depends_on=deps,
        status="PENDING",
        complexity=err.complexity,
        reason=reason or "retry after error",
        meta={"retries": error_step_id},
    )
    ver = plan.replan(
        add_steps=[replacement],
        supersede_ids=[],  # ERROR is finished — not superseded
        reason=reason or f"retry {error_step_id}",
    )
    return {
        "ok": True,
        "version": ver,
        "new_step_id": new_id,
        "error_step_id": error_step_id,
        "error_status": "ERROR",
    }


def plan_blocks_enqueue(plan: LivingPlan, decision_open: bool = False) -> dict[str, Any]:
    """Whether DynamicQueue should wait (plan-level, not FSM)."""
    if decision_open:
        return {"block": True, "reason": "WAITING_DECISION"}
    if has_in_progress(plan):
        return {"block": False, "reason": "in_progress_serial", "serial_only": True}
    elig = eligible_serial(plan)
    if not elig:
        # maybe all done or blocked by ERROR deps
        active = plan.active_steps()
        errs = [s for s in plan.steps if normalize_status(s.status) == "ERROR"]
        if errs and not elig:
            return {
                "block": True,
                "reason": "blocked_by_error_or_deps",
                "error_steps": [s.id for s in errs],
            }
        if not active:
            return {"block": False, "reason": "plan_idle"}
        return {"block": True, "reason": "no_eligible_steps"}
    return {"block": False, "reason": "ok", "next": elig[0].id}
