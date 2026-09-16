# -*- coding: utf-8 -*-
"""FC-30 Decision Queue tests."""
from __future__ import annotations

import time
from pathlib import Path

from intelligence.conflict import ConflictRecord, detect_conflicts
from intelligence.decision_queue import (
    DecisionQueue,
    make_decision_from_conflict,
    options_from_conflict,
)
from intelligence.living_plan import LivingPlan, LivingStep
from intelligence.project_state import ProjectState


def _sample_conflict() -> ConflictRecord:
    return ConflictRecord(
        id="c-db-1",
        topic="database",
        current="sqlite",
        new="postgres",
        affected_step_ids=["s1"],
        recommendation="ask",
        risk="HIGH",
        reason="schema rewrite",
    )


def test_options_abc():
    opts = options_from_conflict(_sample_conflict())
    assert [o.id for o in opts] == ["A", "B", "C"]
    assert opts[0].action == "dismiss"
    assert opts[1].action == "replan"


def test_make_decision_high_no_timeout():
    item = make_decision_from_conflict(_sample_conflict())
    assert item.status == "WAITING_DECISION"
    assert item.risk == "HIGH"
    assert item.timeout_sec == 0.0
    assert item.expires_at == 0.0
    assert "WAITING_DECISION" in item.format_human()


def test_enqueue_and_resolve_replan(tmp_path: Path):
    plan = LivingPlan(
        steps=[
            LivingStep(id="s1", action="sqlite schema", status="PENDING"),
            LivingStep(id="s2", action="ui", status="PENDING"),
        ]
    )
    state = ProjectState()
    q = DecisionQueue(path=tmp_path / "decisions.json")
    conf = _sample_conflict()
    item = q.enqueue_conflict(conf, project="demo")
    assert item.is_open()
    assert q.has_blocking("demo", ["s1"])
    assert not q.has_blocking("demo", ["s2"]) or q.has_blocking("demo", ["s1"])

    result = q.resolve(item.id, "B", plan=plan, state=state, replace_action="postgres schema")
    assert result["ok"]
    assert result["action"] == "replan"
    assert plan.get("s1").status == "SUPERSEDED"
    assert not q.get(item.id).is_open()
    assert state.decisions  # recorded


def test_resolve_dismiss_keeps_steps(tmp_path: Path):
    plan = LivingPlan(steps=[LivingStep(id="s1", action="sqlite", status="PENDING")])
    q = DecisionQueue(path=tmp_path / "d.json")
    item = q.enqueue_conflict(_sample_conflict())
    r = q.resolve(item.id, "A", plan=plan)
    assert r["ok"]
    assert plan.get("s1").status == "PENDING"


def test_expire_medium_not_high(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_DECISION_TIMEOUT_MEDIUM", "1")
    monkeypatch.setenv("AGENTBUS_DECISION_TIMEOUT_HIGH", "0")
    q = DecisionQueue(path=tmp_path / "e.json")
    med = ConflictRecord(
        id="c-m", topic="test_runner", current="pytest", new="unittest",
        recommendation="ask", risk="MEDIUM",
    )
    high = _sample_conflict()
    im = q.enqueue_conflict(med)
    ih = q.enqueue_conflict(high)
    # force medium expired
    im.expires_at = time.time() - 10
    im.timeout_sec = 1
    expired = q.expire_stale()
    assert im.id in expired
    assert q.get(im.id).status == "EXPIRED"
    assert q.get(ih.id).status == "WAITING_DECISION"


def test_persistence(tmp_path: Path):
    path = tmp_path / "persist.json"
    q1 = DecisionQueue(path=path)
    q1.enqueue_conflict(_sample_conflict(), project="p1")
    q2 = DecisionQueue(path=path)
    assert len(q2.open_items()) == 1
    assert q2.open_items()[0].project == "p1"


def test_detect_then_decision_pipeline():
    plan = LivingPlan(
        summary="sqlite",
        steps=[LivingStep(id="db", action="setup sqlite", status="PENDING")],
    )
    conflicts = detect_conflicts("switch to PostgreSQL", plan=plan)
    assert conflicts
    item = make_decision_from_conflict(conflicts[0])
    assert item.conflict_id
    assert item.options
