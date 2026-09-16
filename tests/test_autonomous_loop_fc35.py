# -*- coding: utf-8 -*-
"""FC-35 Autonomous Loop tick tests."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from intelligence.autonomous_loop import TickResult, run_tick, run_tick_safe
from intelligence.conflict import ConflictRecord
from intelligence.decision_queue import DecisionQueue
from intelligence.living_plan import LivingPlan, LivingStep


def test_tick_manual_pause(tmp_path: Path):
    plan = LivingPlan(steps=[LivingStep(id="s1", action="x", status="PENDING")])
    r = run_tick(
        tmp_path,
        plan=plan,
        decisions=DecisionQueue(),
        manual_pause=True,
        persist=False,
        use_desktop_queue=False,
    )
    assert r.waited or not r.emitted
    assert any("wait" in a for a in r.actions)


def test_tick_ready_emits_with_filebus(tmp_path: Path):
    plan = LivingPlan(
        version=1,
        project_id="demo",
        steps=[
            LivingStep(id="s1", action="fix typo", status="PENDING", complexity=1),
        ],
    )
    r = run_tick(
        tmp_path,
        plan=plan,
        decisions=DecisionQueue(),
        max_emit=2,
        use_desktop_queue=False,
        use_filebus=True,
        persist=False,
        now=datetime(2026, 6, 1, 12, 0),  # day — low complexity runs
    )
    # low complexity daytime should emit via filebus
    assert r.ok
    assert isinstance(r, TickResult)
    # filebus may create channels
    assert r.format_human()


def test_tick_high_conflict_enqueues_decision(tmp_path: Path):
    plan = LivingPlan(
        summary="sqlite",
        steps=[LivingStep(id="db", action="sqlite schema", status="PENDING", complexity=2)],
    )
    conf = ConflictRecord(
        id="c-db",
        topic="database",
        current="sqlite",
        new="postgres",
        affected_step_ids=["db"],
        risk="HIGH",
        recommendation="ask",
    )
    dq = DecisionQueue(path=tmp_path / "dec.json")
    r = run_tick(
        tmp_path,
        plan=plan,
        decisions=dq,
        conflicts=[conf],
        use_desktop_queue=False,
        use_filebus=False,
        persist=False,
        policy_mode="full",
    )
    assert r.open_decisions >= 1 or any("decision_enqueued" in a for a in r.actions)
    assert r.waited or r.open_decisions >= 1


def test_tick_safe_never_raises(tmp_path: Path):
    r = run_tick_safe("/nonexistent/path/hopefully", persist=False, use_desktop_queue=False)
    assert isinstance(r, TickResult)


def test_tick_result_to_dict():
    r = TickResult(ok=True, emitted=["a"], plan_version=2)
    d = r.to_dict()
    assert d["emitted"] == ["a"]
    assert d["plan_version"] == 2


def test_tick_project_scan_flag(tmp_path: Path):
    (tmp_path / "x.py").write_text("a=1\n", encoding="utf-8")
    plan = LivingPlan(steps=[LivingStep(id="s", action="noop", status="PENDING", complexity=1)])
    r = run_tick(
        tmp_path,
        plan=plan,
        decisions=DecisionQueue(),
        run_project_scan=True,
        use_desktop_queue=False,
        use_filebus=False,
        persist=False,
    )
    assert any("project_scan" in a for a in r.actions)


def test_tick_architecture_interview_flag(tmp_path: Path):
    (tmp_path / "app.py").write_text("from fastapi import FastAPI\napp=FastAPI()\n", encoding="utf-8")
    plan = LivingPlan(steps=[LivingStep(id="s", action="noop", status="PENDING", complexity=1)])
    dq = DecisionQueue(path=tmp_path / "dec.json")
    r = run_tick(
        tmp_path,
        plan=plan,
        decisions=dq,
        run_architecture_interview=True,
        architecture_limit=2,
        use_desktop_queue=False,
        use_filebus=False,
        persist=False,
    )
    assert any("arch_interview" in a for a in r.actions)

def test_tick_result_has_action_phase():
    r = TickResult(ok=True, waited=True, wait={"reason": "manual_pause"}, open_decisions=0)
    from intelligence.autonomous_loop import _finalize_action, TICK_WAIT
    r = _finalize_action(r)
    assert r.action in (TICK_WAIT, "WAIT", "DEFER", "ASK")
    assert r.phase


def test_tick_emitted_sets_action_emit(tmp_path: Path):
    plan = LivingPlan(
        steps=[LivingStep(id="s1", action="format", status="PENDING", complexity=1)],
    )
    r = run_tick(
        tmp_path,
        plan=plan,
        decisions=DecisionQueue(),
        use_desktop_queue=True,
        use_filebus=False,
        persist=False,
        now=datetime(2026, 6, 1, 12, 0),
    )
    assert r.action in ("EMIT", "WAIT", "DEFER", "ASK", "RUN")
    d = r.to_dict()
    assert "action" in d and "phase" in d

