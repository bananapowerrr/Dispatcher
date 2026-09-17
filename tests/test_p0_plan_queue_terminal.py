# -*- coding: utf-8 -*-
from pathlib import Path
from intelligence.living_plan import LivingPlan, LivingStep, save_living_plan, load_living_plan
from intelligence.dynamic_queue import (
    on_task_terminal,
    notify_plan_task_terminal,
    _step_task_payload,
)

def test_step_payload_has_plan_identity():
    plan = LivingPlan(version=3, project_id="demo")
    step = LivingStep(id="s1", action="Add tests", status="PENDING")
    plan.steps.append(step)
    p = _step_task_payload(step, plan=plan, project="demo")
    assert p["metadata"]["source"] == "living_plan"
    assert p["metadata"]["plan_version"] == 3
    assert p["metadata"]["plan_step_id"] == "s1"

def test_on_task_terminal_marks_done():
    plan = LivingPlan(version=1)
    step = LivingStep(id="a", action="X", status="READY", meta={"task_id": "t-1"})
    plan.steps.append(step)
    assert on_task_terminal(plan, task_id="t-1", status="DONE")
    assert plan.get("a").status == "DONE"

def test_notify_persists(tmp_path: Path):
    plan = LivingPlan(version=1, project_id="p")
    plan.steps.append(
        LivingStep(id="b", action="Y", status="READY", meta={"task_id": "plan-1-b", "source": "living_plan"})
    )
    save_living_plan(tmp_path, plan)
    ok = notify_plan_task_terminal(
        tmp_path, task_id="plan-1-b", plan_step_id="b", status="DONE",
        metadata={"source": "living_plan"},
    )
    assert ok
    assert load_living_plan(tmp_path).get("b").status == "DONE"

def test_dynamic_queue_strict_no_bypass():
    src = Path("src/intelligence/dynamic_queue.py").read_text(encoding="utf-8")
    assert "soft_intake=False" in src
    assert "fallback: local queue direct" not in src
    block = src.split("def sync_plan_to_queue")[1].split("def sync_from_disk")[0]
    assert "get_local_queue" not in block

def test_editor_buffer_slot():
    src = Path("ui/editor_panel.py").read_text(encoding="utf-8")
    assert "buffer" in src
    assert "st_old.buffer" in src or "st.buffer" in src

def test_runtime_has_plan_hook():
    src = Path("src/core/runtime.py").read_text(encoding="utf-8")
    assert "notify_plan_task_terminal" in src

def test_continue_doc():
    from app.post_step_report import continue_selected
    assert "LivingPlan" in (continue_selected.__doc__ or "")
