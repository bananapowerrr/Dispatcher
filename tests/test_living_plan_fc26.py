# -*- coding: utf-8 -*-
"""FC-26 Living Plan."""
from __future__ import annotations

from intelligence.living_plan import (
    LivingPlan,
    LivingStep,
    load_living_plan,
    save_living_plan,
    is_finished,
    is_active,
)
from intelligence.task_graph import TaskGraph, GraphNode
from intelligence.pev_loop import Plan, PlanStep


def test_supersede_preserves_done():
    plan = LivingPlan(summary="auth", version=1)
    plan.steps = [
        LivingStep(id="s1", action="old auth", status="DONE"),
        LivingStep(id="s2", action="old reset", status="PENDING"),
        LivingStep(id="s3", action="tests", status="PENDING", depends_on=["s2"]),
    ]
    assert plan.supersede("s1", reason="nope") is None  # DONE frozen
    assert plan.get("s1").status == "DONE"
    new_id = plan.supersede(
        "s2",
        reason="new auth mechanism",
        replacement=LivingStep(id="s2b", action="new auth"),
    )
    assert new_id == "s2b"
    assert plan.get("s2").status == "SUPERSEDED"
    assert plan.get("s2").replaced_by == "s2b"
    assert plan.get("s2b").status == "PENDING"


def test_replan_bumps_version(tmp_path):
    plan = LivingPlan(summary="v1", version=1, steps=[
        LivingStep(id="a", action="sqlite", status="PENDING"),
        LivingStep(id="b", action="ui", status="PENDING"),
    ])
    v = plan.replan(
        summary="postgres instead",
        supersede_ids=["a"],
        add_steps=[LivingStep(id="a2", action="postgres")],
        reason="user decision",
    )
    assert v == 2
    assert plan.get("a").status == "SUPERSEDED"
    assert plan.get("a2").action == "postgres"
    assert len(plan.history) == 1
    path = save_living_plan(tmp_path, plan)
    loaded = load_living_plan(tmp_path)
    assert loaded.version == 2
    assert loaded.get("a").status == "SUPERSEDED"


def test_eligible_skips_inactive():
    plan = LivingPlan(steps=[
        LivingStep(id="1", action="done", status="DONE"),
        LivingStep(id="2", action="old", status="SUPERSEDED"),
        LivingStep(id="3", action="next", status="PENDING", depends_on=["1"]),
        LivingStep(id="4", action="blocked", status="PENDING", depends_on=["2"]),
    ])
    el = plan.eligible_for_queue()
    ids = [s.id for s in el]
    assert "3" in ids
    assert "2" not in ids
    assert "4" not in ids  # dep superseded, not DONE


def test_from_pev_plan():
    pev = Plan(
        task_id="t1",
        summary="refactor",
        steps=[PlanStep(action="extract", target="fn"), PlanStep(action="tests")],
        files=["a.py"],
    )
    lp = LivingPlan.from_pev_plan(pev, project_id="proj")
    assert len(lp.steps) == 2
    assert lp.steps[0].files == ["a.py"]


def test_task_graph_ignores_superseded():
    g = TaskGraph()
    g.nodes["a"] = GraphNode(id="a", message="x", status="SUPERSEDED")
    g.nodes["b"] = GraphNode(id="b", message="y", status="PENDING")
    ready = g.ready()
    ids = [n.id for n in ready]
    assert "a" not in ids
    assert "b" in ids
    assert not g.all_finished()
    g.nodes["b"].status = "CANCELLED"
    assert g.all_finished()


def test_status_helpers():
    assert is_finished("DONE")
    assert not is_active("SUPERSEDED")
    assert is_active("PENDING")
