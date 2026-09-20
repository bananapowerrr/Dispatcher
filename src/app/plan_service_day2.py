# -*- coding: utf-8 -*-
"""PlanService extensions for Day-2 task outcome (imported by tests / facade)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.plan_service import PlanService
from intelligence.plan_runtime_bridge import (
    apply_task_outcome,
    eligible_serial,
    next_step,
    plan_blocks_enqueue,
    replan_after_error,
)


def on_task_outcome(
    project_root: str | Path,
    step_id: str,
    *,
    task_status: str,
    task_id: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """Persist plan step status from task lifecycle — never declares task DONE."""
    svc = PlanService(project_root)
    plan = svc.load()
    out = apply_task_outcome(
        plan, step_id, task_status=task_status, task_id=task_id, reason=reason
    )
    if out.get("ok"):
        svc.save(plan)
    out["eligible"] = [s.id for s in eligible_serial(plan)]
    nxt = next_step(plan)
    out["next_step_id"] = nxt.id if nxt else ""
    return out


def get_serial_eligible(project_root: str | Path) -> list[dict[str, Any]]:
    plan = PlanService(project_root).load()
    return [s.to_dict() for s in eligible_serial(plan)]


def retry_error_step(
    project_root: str | Path,
    error_step_id: str,
    *,
    new_action: str = "",
    reason: str = "",
) -> dict[str, Any]:
    svc = PlanService(project_root)
    plan = svc.load()
    out = replan_after_error(
        plan, error_step_id, new_action=new_action, reason=reason
    )
    if out.get("ok"):
        svc.save(plan)
        out["plan"] = svc.list_plan()
    return out


def enqueue_gate(project_root: str | Path, *, decision_open: bool = False) -> dict[str, Any]:
    plan = PlanService(project_root).load()
    return plan_blocks_enqueue(plan, decision_open=decision_open)
