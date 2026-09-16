# -*- coding: utf-8 -*-
"""FC-33 Estimation tests."""
from __future__ import annotations

from intelligence.estimation import (
    apply_estimates_to_plan,
    estimate_step,
    estimate_text,
    heuristic_complexity,
    plan_total_estimate,
    record_outcome,
)
from intelligence.living_plan import LivingPlan, LivingStep


def test_docs_low_complexity():
    cx, _ = heuristic_complexity("обнови README и docstring")
    assert cx <= 2


def test_refactor_high():
    cx, reasons = heuristic_complexity("полный refactor auth module", files=["a.py", "b.py", "c.py", "d.py"])
    assert cx >= 4
    assert reasons


def test_estimate_text_format():
    e = estimate_text("add unit tests for parser")
    assert 1 <= e.complexity <= 5
    assert e.duration_sec >= 15
    assert "complexity=" in e.format_human()


def test_history_blend():
    hist = [
        {"message": "add unit tests for parser", "duration_sec": 200, "complexity": 3, "status": "DONE", "ok": True},
        {"message": "add unit tests for router", "duration_sec": 180, "complexity": 3, "status": "DONE", "ok": True},
    ]
    e = estimate_text("add unit tests for parser", history=hist)
    assert e.source == "hybrid"
    assert e.samples >= 2
    assert e.duration_sec > 15


def test_estimate_step_and_plan():
    plan = LivingPlan(
        steps=[
            LivingStep(id="1", action="format imports", status="PENDING", complexity=1),
            LivingStep(id="2", action="refactor payment flow", status="PENDING", files=["p.py", "q.py"], complexity=3),
            LivingStep(id="3", action="old", status="DONE"),
        ]
    )
    rows = apply_estimates_to_plan(plan)
    assert len(rows) == 2
    assert "estimate" in (plan.get("1").meta or {})
    total = plan_total_estimate(plan)
    assert total["steps"] == 2
    assert total["total_duration_sec"] > 0


def test_record_outcome_bounds():
    buf: list = []
    for i in range(5):
        record_outcome(buf, message=f"task {i}", duration_sec=10 + i, complexity=2, ok=True, limit=3)
    assert len(buf) == 3
