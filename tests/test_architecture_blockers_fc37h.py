# -*- coding: utf-8 -*-
"""FC-37H Architecture blockers tests."""
from __future__ import annotations

from pathlib import Path

from intelligence.architecture_blockers import (
    format_blocker_banner,
    has_architecture_blockers,
    open_architecture_decisions,
    evaluate_architecture_gate,
)
from intelligence.architecture_interview import make_architecture_decision, start_interview
from intelligence.decision_queue import DecisionQueue
from intelligence.living_plan import LivingPlan, LivingStep
from intelligence.smart_waiting import REASON_ARCHITECTURE, evaluate_wait, filter_emit_steps


def test_architecture_decision_blocks_emit():
    dq = DecisionQueue()
    item = make_architecture_decision("Где бизнес-логика — в UI, в API или разделена?")
    dq.enqueue(item)
    w = evaluate_wait(decisions=dq, check_night=False)
    assert not w.can_emit
    assert w.reason == REASON_ARCHITECTURE
    assert item.id in w.blocking_decision_ids


def test_filter_holds_all_without_step_ids():
    dq = DecisionQueue()
    dq.enqueue(make_architecture_decision("Какая точка входа в приложение?"))
    w = evaluate_wait(decisions=dq, check_night=False)
    steps = [
        LivingStep(id="a", action="x", status="PENDING"),
        LivingStep(id="b", action="y", status="PENDING"),
    ]
    allow, hold = filter_emit_steps(steps, w)
    assert allow == []
    assert len(hold) == 2


def test_helpers(tmp_path: Path):
    dq = DecisionQueue(path=tmp_path / "d.json")
    assert not has_architecture_blockers(dq)
    dq.enqueue(make_architecture_decision("Где источник истины для данных?"))
    assert has_architecture_blockers(dq)
    assert open_architecture_decisions(dq)
    banner = format_blocker_banner(dq)
    assert "стопор" in banner.lower() or "Архитектур" in banner
    gate = evaluate_architecture_gate(dq)
    assert gate.reason == REASON_ARCHITECTURE


def test_resolved_clears_block():
    dq = DecisionQueue()
    item = make_architecture_decision("Как запускать проверки после изменений?")
    dq.enqueue(item)
    item.status = "RESOLVED"
    w = evaluate_wait(decisions=dq, check_night=False)
    assert w.can_emit
