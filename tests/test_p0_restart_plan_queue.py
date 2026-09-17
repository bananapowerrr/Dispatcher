# -*- coding: utf-8 -*-
"""P0: plan + queue survive process boundary (spill + disk plan)."""
from __future__ import annotations

from pathlib import Path

from intelligence.living_plan import LivingPlan, LivingStep, save_living_plan, load_living_plan
from intelligence.dynamic_queue import notify_plan_task_terminal, mark_step_emitted, _step_task_payload
from core.local_queue import get_local_queue, reset_local_queue
from app.plan_service import PlanService


def test_plan_survives_reload(tmp_path: Path):
    plan = LivingPlan(version=1, summary="s")
    step = LivingStep(id="x", action="Work", status="READY")
    mark_step_emitted(step, "plan-1-x")
    plan.steps.append(step)
    save_living_plan(tmp_path, plan)
    loaded = load_living_plan(tmp_path)
    assert loaded.get("x").meta.get("task_id") == "plan-1-x"
    assert loaded.get("x").meta.get("emitted") is True


def test_terminal_after_reload(tmp_path: Path):
    plan = LivingPlan(version=1)
    step = LivingStep(id="y", action="Y", status="READY", meta={"task_id": "tid-y", "source": "living_plan"})
    plan.steps.append(step)
    save_living_plan(tmp_path, plan)
    # simulate new process: only disk
    ok = notify_plan_task_terminal(
        tmp_path, task_id="tid-y", plan_step_id="y", status="DONE",
        metadata={"source": "living_plan"},
    )
    assert ok
    assert load_living_plan(tmp_path).get("y").status == "DONE"


def test_queue_spill_survives_reset(tmp_path: Path):
    reset_local_queue()
    q1 = get_local_queue(tmp_path)
    tid = q1.put({
        "id": "t-spill",
        "message": "from ui",
        "metadata": {"plan_step_id": "s1", "source": "living_plan"},
    })
    assert tid
    # simulate dispatcher process
    reset_local_queue()
    q2 = get_local_queue(tmp_path)
    claimed = q2.claim()
    assert claimed is not None
    assert claimed.get("id") == "t-spill" or claimed.get("message") == "from ui"
    assert (claimed.get("metadata") or {}).get("plan_step_id") == "s1"


def test_plan_identity_in_payload_after_service(tmp_path: Path):
    plan = LivingPlan(version=5, project_id="p")
    step = LivingStep(id="z", action="Z", status="PENDING")
    plan.steps.append(step)
    save_living_plan(tmp_path, plan)
    p = _step_task_payload(step, plan=plan, project="p")
    assert p["metadata"]["plan_version"] == 5
    assert p["metadata"]["plan_step_id"] == "z"


def test_done_frozen_across_reload(tmp_path: Path):
    plan = LivingPlan(version=1)
    plan.steps.append(LivingStep(id="d", action="D", status="DONE"))
    save_living_plan(tmp_path, plan)
    PlanService(tmp_path).replan(supersede_ids=["d"], reason="nope")
    assert load_living_plan(tmp_path).get("d").status == "DONE"
