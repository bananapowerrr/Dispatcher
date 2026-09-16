# -*- coding: utf-8 -*-
"""FC-34 Night Mode polish tests."""
from __future__ import annotations

from datetime import datetime, time as dtime

from intelligence.living_plan import LivingPlan, LivingStep
from intelligence.night_scheduler import NightConfig, NightScheduler


def test_is_night_cross_midnight():
    cfg = NightConfig(start=dtime(22, 0), end=dtime(6, 0))
    sched = NightScheduler(cfg)
    assert sched.is_night(datetime(2026, 1, 1, 23, 0))
    assert sched.is_night(datetime(2026, 1, 2, 3, 0))
    assert not sched.is_night(datetime(2026, 1, 1, 12, 0))


def test_defer_complex_day():
    sched = NightScheduler(NightConfig(min_complexity=3))
    noon = datetime(2026, 6, 1, 12, 0)
    assert sched.should_defer_to_night({"complexity": 4}, now=noon)
    assert not sched.should_defer_to_night({"complexity": 1}, now=noon)
    assert not sched.should_defer_to_night({"complexity": 5, "urgent": True}, now=noon)


def test_select_with_duration_budget():
    cfg = NightConfig(min_complexity=3, max_tasks_per_night=10, max_duration_sec=200)
    sched = NightScheduler(cfg)
    tasks = [
        {"id": "a", "complexity": 5, "priority": 5, "metadata": {"estimate": {"duration_sec": 150}}},
        {"id": "b", "complexity": 4, "priority": 4, "metadata": {"estimate": {"duration_sec": 150}}},
        {"id": "c", "complexity": 3, "priority": 3, "metadata": {"estimate": {"duration_sec": 40}}},
    ]
    chosen = sched.select_night_tasks(tasks)
    ids = [t["id"] for t in chosen]
    assert "a" in ids
    # b would exceed 200 after a → skip; c may fit
    assert "b" not in ids or sum(
        t["metadata"]["estimate"]["duration_sec"] for t in chosen
    ) <= 200 + 1


def test_plan_steps_for_night():
    plan = LivingPlan(
        steps=[
            LivingStep(id="light", action="fix typo", status="PENDING", complexity=1),
            LivingStep(id="heavy", action="refactor module", status="PENDING", complexity=5),
            LivingStep(id="done", action="x", status="DONE", complexity=5),
        ]
    )
    sched = NightScheduler(NightConfig(min_complexity=3))
    steps = sched.select_plan_steps_for_night(plan, apply_estimates=True)
    ids = [s.id for s in steps]
    assert "heavy" in ids
    assert "light" not in ids
    assert "done" not in ids


def test_night_batch_summary():
    sched = NightScheduler()
    plan = LivingPlan(steps=[LivingStep(id="h", action="big", complexity=5, status="PENDING")])
    s = sched.night_batch_summary(plan=plan, pending_tasks=[{"id": "t1", "complexity": 4}])
    assert "window" in s
    assert "h" in s["step_ids"]
    assert "t1" in s["task_ids"]


def test_morning_report_rich():
    sched = NightScheduler()
    text = sched.generate_morning_report_rich(
        [
            {"status": "DONE", "message": "ok", "worker": "aider", "duration_sec": 90},
            {"status": "ERROR", "message": "bad", "error": "fail"},
        ],
        plan_version=3,
        decisions_open=1,
    )
    assert "Успешно" in text or "DONE" in text
    assert "Версия плана: 3" in text
    assert "Открытых решений: 1" in text
    assert "мин" in text
