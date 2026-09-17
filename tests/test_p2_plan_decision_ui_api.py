# -*- coding: utf-8 -*-
"""Plan panel uses same resolve API as DecisionQueue."""
from pathlib import Path
from intelligence.living_plan import LivingPlan, LivingStep, save_living_plan, load_living_plan
from app.plan_service import apply_input_policy, resolve_plan_decision, get_decision_queue

def test_resolve_a_dismiss_keeps_plan(tmp_path: Path):
    plan = LivingPlan(version=1)
    plan.steps.append(LivingStep(id="a", action="Keep me", status="PENDING"))
    save_living_plan(tmp_path, plan)
    r = apply_input_policy(tmp_path, "перепланируй с нуля")
    did = r["decision_id"]
    out = resolve_plan_decision(tmp_path, did, "A")  # dismiss
    assert out["ok"]
    assert load_living_plan(tmp_path).get("a").status == "PENDING"
    assert not get_decision_queue(tmp_path).open_items()

def test_editor_has_shortcuts():
    src = Path("ui/editor_panel.py").read_text(encoding="utf-8")
    assert "Control-s" in src
    assert "_on_ctrl_tab" in src

def test_plan_panel_has_resolve():
    src = Path("ui/plan_panel.py").read_text(encoding="utf-8")
    assert "_resolve_opt" in src
    assert "resolve_plan_decision" in src
