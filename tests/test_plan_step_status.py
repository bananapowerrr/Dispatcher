# -*- coding: utf-8 -*-
from pathlib import Path
from intelligence.living_plan import LivingPlan, LivingStep, save_living_plan
from app.plan_service import PlanService

def test_set_step_status(tmp_path: Path):
    (tmp_path / ".agentbus").mkdir(parents=True, exist_ok=True)
    plan = LivingPlan(project_id=str(tmp_path))
    plan.steps.append(LivingStep(id="s1", action="x", status="PENDING"))
    save_living_plan(tmp_path, plan)
    r = PlanService(tmp_path).set_step_status("s1", "IN_PROGRESS", task_id="tid")
    assert r["ok"]
    s = PlanService(tmp_path).get_step("s1")
    assert s["status"] == "IN_PROGRESS"
    assert s["meta"]["task_id"] == "tid"
