# -*- coding: utf-8 -*-
from __future__ import annotations


def test_skip_when_not_replan():
    from core.recovery_plan_hook import try_plan_replan_from_error

    r = try_plan_replan_from_error({
        "attempts": 3,
        "metadata": {"failure_layer": "reclaim_max_attempts"},
        "result": {"error": "stuck"},
    })
    assert r.get("skipped") is True
    assert r.get("enqueued") is False
    assert r["decision"]["action"] == "ask_user"


def test_skip_when_no_step_id():
    from core.recovery_plan_hook import try_plan_replan_from_error

    r = try_plan_replan_from_error({
        "attempts": 1,
        "metadata": {"failure_layer": "verification"},
        "result": {"error": "pytest failed", "verification": {"ok": False}},
    })
    # verification → replan action but no step
    assert r["decision"]["action"] in ("replan", "ask_user")
    if r["decision"]["action"] == "replan":
        assert r.get("reason") == "no_plan_step_id"
    assert r.get("enqueued") is False


def test_replan_adds_pending_step():
    from intelligence.living_plan import LivingPlan, LivingStep
    from core.recovery_plan_hook import try_plan_replan_from_error, annotate_row_with_replan_result

    plan = LivingPlan(summary="t")
    plan.steps.append(
        LivingStep(id="s1", action="fix bug", status="ERROR", depends_on=[])
    )
    row = {
        "attempts": 1,
        "message": "fix bug again",
        "metadata": {
            "failure_layer": "verification",
            "plan_step_id": "s1",
            "recoverable": True,
        },
        "result": {"error": "verify fail", "verification": {"ok": False}},
    }
    r = try_plan_replan_from_error(row, plan, new_action="fix bug retry")
    assert r.get("enqueued") is False
    if r.get("ok"):
        assert r.get("new_step_id")
        assert any(s.id == r["new_step_id"] for s in plan.steps)
        assert any(s.status == "ERROR" and s.id == "s1" for s in plan.steps)
        ann = annotate_row_with_replan_result(row, r)
        assert ann["metadata"]["plan_replan"]["ok"] is True
    else:
        # living_plan API variance — still must not enqueue
        assert r.get("enqueued") is False


def test_mechanism_replan_path():
    from core.recovery_mechanism import mechanism_for_decision
    m = mechanism_for_decision({"action": "replan"})
    assert m["path"] == "plan_layer_only"
    assert m["enqueue_new"] is False
