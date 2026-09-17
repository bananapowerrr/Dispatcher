# -*- coding: utf-8 -*-
from pathlib import Path
from intelligence.living_plan import LivingPlan, LivingStep, save_living_plan, load_living_plan
from intelligence.dynamic_queue import sync_plan_to_queue
from app.plan_service import (
    apply_input_policy,
    resolve_plan_decision,
    get_decision_queue,
    PlanService,
)

def test_replan_enqueues_decision_not_mutate(tmp_path: Path):
    plan = LivingPlan(version=1, summary="s")
    plan.steps.append(LivingStep(id="a", action="Old", status="PENDING"))
    save_living_plan(tmp_path, plan)
    r = apply_input_policy(tmp_path, "перепланируй с нуля oauth", enqueue_decision=True)
    assert r["classification"] == "REPLAN"
    assert r["requires_decision"] is True
    assert r["applied"] is False
    assert r["decision_id"]
    # plan unchanged
    assert load_living_plan(tmp_path).get("a").status == "PENDING"
    q = get_decision_queue(tmp_path)
    assert q.has_blocking("")

def test_resolve_replan_pending(tmp_path: Path):
    plan = LivingPlan(version=1)
    plan.steps.append(LivingStep(id="a", action="Old", status="PENDING"))
    save_living_plan(tmp_path, plan)
    r = apply_input_policy(tmp_path, "перепланируй архитектуру", enqueue_decision=True)
    did = r["decision_id"]
    out = resolve_plan_decision(tmp_path, did, "C")  # replan_pending
    assert out["ok"]
    loaded = load_living_plan(tmp_path)
    assert loaded.get("a").status == "SUPERSEDED"
    assert loaded.version >= 2

def test_emit_blocked_when_decision_open(tmp_path: Path):
    plan = LivingPlan(version=1, project_id="p")
    plan.steps.append(LivingStep(id="a", action="Do", status="PENDING"))
    save_living_plan(tmp_path, plan)
    apply_input_policy(tmp_path, "перепланируй с нуля")
    plan = load_living_plan(tmp_path)
    er = sync_plan_to_queue(plan, project_root=tmp_path, project="p", max_emit=2)
    assert any("blocked" in e for e in er.errors)
    assert not er.emitted

def test_add_auto_no_decision(tmp_path: Path):
    save_living_plan(tmp_path, LivingPlan(version=1))
    r = apply_input_policy(tmp_path, "добавь в план логирование", auto=True, enqueue_decision=True)
    assert r["classification"] == "ADD"
    assert r["applied"] is True
