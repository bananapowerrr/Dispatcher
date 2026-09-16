# -*- coding: utf-8 -*-
"""FC-29 Conflict detection and resolution."""
from __future__ import annotations

from intelligence.conflict import detect_conflicts, apply_conflict_resolution, ConflictRecord
from intelligence.living_plan import LivingPlan, LivingStep
from intelligence.project_state import ProjectState


def test_sqlite_vs_postgres():
    plan = LivingPlan(
        summary="Use SQLite for storage",
        steps=[
            LivingStep(id="s1", action="setup sqlite schema", status="PENDING"),
            LivingStep(id="s2", action="UI polish", status="PENDING"),
        ],
    )
    conflicts = detect_conflicts(
        "Переходим на PostgreSQL вместо SQLite",
        plan=plan,
    )
    assert conflicts
    c = conflicts[0]
    assert c.topic == "database"
    assert "s1" in c.affected_step_ids
    assert c.recommendation in ("replan", "ask")


def test_no_conflict_when_aligned():
    plan = LivingPlan(
        summary="pytest everywhere",
        steps=[LivingStep(id="t", action="add pytest coverage", status="PENDING")],
    )
    conflicts = detect_conflicts("добавь ещё pytest тесты", plan=plan)
    assert conflicts == []


def test_local_constraint_vs_cloud():
    state = ProjectState()
    state.add_constraint("только локально, no cloud")
    conflicts = detect_conflicts(
        "подключи OpenRouter для worker",
        state=state,
    )
    assert any(c.topic == "cloud" for c in conflicts)
    assert any(c.risk == "HIGH" for c in conflicts)


def test_apply_replan_supersedes():
    plan = LivingPlan(
        version=1,
        steps=[
            LivingStep(id="db", action="sqlite migrations", status="PENDING"),
            LivingStep(id="ui", action="forms", status="PENDING"),
        ],
    )
    c = ConflictRecord(
        id="c1",
        topic="database",
        current="sqlite",
        new="postgres",
        affected_step_ids=["db"],
        recommendation="replan",
        risk="HIGH",
    )
    acts = apply_conflict_resolution(
        c, plan, resolution="replan", replace_action="postgres migrations"
    )
    assert "replan" in acts
    assert plan.get("db").status == "SUPERSEDED"
    assert plan.version == 2
    assert any(s.action.startswith("postgres") for s in plan.steps)


def test_dismiss():
    plan = LivingPlan(steps=[LivingStep(id="a", action="x", status="PENDING")])
    c = ConflictRecord(
        id="c2", topic="x", current="a", new="b", recommendation="replan"
    )
    acts = apply_conflict_resolution(c, plan, resolution="dismiss")
    assert acts == ["dismissed"]
    assert c.status == "DISMISSED"
    assert plan.get("a").status == "PENDING"


def test_format_human():
    c = ConflictRecord(
        id="c3",
        topic="auth",
        current="jwt",
        new="oauth",
        affected_step_ids=["a1"],
        recommendation="ask",
        risk="HIGH",
        reason="auth rewrite",
    )
    text = c.format_human()
    assert "CONFLICT" in text and "oauth" in text
