# -*- coding: utf-8 -*-
"""FC-32 Smart Waiting tests."""
from __future__ import annotations

from datetime import datetime

from intelligence.conflict import ConflictRecord
from intelligence.decision_queue import DecisionQueue, make_decision_from_conflict
from intelligence.living_plan import LivingPlan, LivingStep
from intelligence.smart_waiting import (
    REASON_DECISION,
    REASON_MANUAL,
    REASON_NIGHT,
    REASON_NONE,
    REASON_POLICY_ASK,
    evaluate_wait,
    filter_emit_steps,
    after_decision_resolved,
)


def test_ready_no_blockers():
    w = evaluate_wait(check_night=False)
    assert w.can_emit and w.can_run
    assert w.reason == REASON_NONE
    assert not w.is_waiting()


def test_manual_pause():
    w = evaluate_wait(manual_pause=True)
    assert w.reason == REASON_MANUAL
    assert not w.can_emit and not w.can_run


def test_open_decision_blocks_emit():
    conf = ConflictRecord(
        id="c1", topic="database", current="sqlite", new="pg",
        affected_step_ids=["s1"], recommendation="ask", risk="HIGH",
    )
    q = DecisionQueue()
    q.enqueue_conflict(conf, project="p")
    w = evaluate_wait(decisions=q, project="p", check_night=False)
    assert w.reason == REASON_DECISION
    assert not w.can_emit
    assert w.can_run  # other work ok
    assert "s1" in w.blocked_step_ids


def test_filter_emit_partial():
    steps = [
        LivingStep(id="s1", action="db", status="PENDING"),
        LivingStep(id="s2", action="ui", status="PENDING"),
    ]
    conf = ConflictRecord(
        id="c1", topic="database", current="a", new="b",
        affected_step_ids=["s1"], risk="HIGH",
    )
    q = DecisionQueue()
    q.enqueue_conflict(conf)
    w = evaluate_wait(decisions=q, check_night=False)
    allow, hold = filter_emit_steps(steps, w)
    assert [s.id for s in hold] == ["s1"]
    assert [s.id for s in allow] == ["s2"]


def test_policy_high_ask():
    conf = ConflictRecord(
        id="c2", topic="auth", current="jwt", new="oauth",
        risk="HIGH", recommendation="ask",
    )
    w = evaluate_wait(conflicts=[conf], check_night=False, policy_mode="full")
    assert w.reason == REASON_POLICY_ASK
    assert not w.can_emit


def test_night_defers_complex_daytime():
    plan = LivingPlan(
        steps=[
            LivingStep(id="h", action="big refactor", status="PENDING", complexity=5),
        ]
    )
    # noon
    noon = datetime(2026, 6, 15, 12, 0, 0)
    w = evaluate_wait(plan=plan, now=noon, check_night=True, policy_mode="balanced")
    assert w.reason == REASON_NIGHT
    assert not w.can_emit
    assert "h" in w.blocked_step_ids


def test_after_resolve_clears():
    conf = ConflictRecord(
        id="c3", topic="x", current="a", new="b",
        affected_step_ids=["s1"], risk="HIGH",
    )
    q = DecisionQueue()
    item = q.enqueue_conflict(conf)
    plan = LivingPlan(steps=[LivingStep(id="s1", action="x", status="PENDING")])
    q.resolve(item.id, "A", plan=plan)
    w = after_decision_resolved(q, plan)
    assert w.reason == REASON_NONE or w.can_emit


def test_format_human_waiting():
    w = evaluate_wait(manual_pause=True)
    assert "WAITING" in w.format_human()
