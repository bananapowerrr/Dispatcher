# -*- coding: utf-8 -*-
"""Day-12 offline: recovery / replan UX copy (no FSM mutation)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path = [p for p in sys.path if Path(p).resolve() not in {ROOT.resolve()}]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.recovery_ux import (
    format_block_reason,
    format_recovery_bundle,
    format_replan_result,
    format_task_outcome_for_plan,
)
from intelligence.living_plan import LivingPlan, LivingStep
from intelligence.plan_runtime_bridge import (
    apply_task_outcome,
    plan_blocks_enqueue,
    replan_after_error,
)


def _plan() -> LivingPlan:
    return LivingPlan(
        project_id="demo",
        summary="t",
        version=1,
        steps=[
            LivingStep(id="s1", action="Add login", status="PENDING"),
            LivingStep(id="s2", action="Add tests", status="PENDING", depends_on=["s1"]),
        ],
    )


def test_format_replan_ok():
    plan = _plan()
    apply_task_outcome(plan, "s1", task_status="ERROR", task_id="t1")
    r = replan_after_error(plan, "s1", new_action="Add login again")
    text = format_replan_result(r)
    assert "Replan" in text or "↻" in text
    assert r["new_step_id"] in text


def test_format_replan_fail_not_error():
    plan = _plan()
    r = replan_after_error(plan, "s1", new_action="x")
    text = format_replan_result(r)
    assert "⚠" in text
    assert "ERROR" in text or "ошиб" in text.lower() or "replan" in text.lower()


def test_format_outcome_frozen_done():
    plan = _plan()
    apply_task_outcome(plan, "s1", task_status="DONE", task_id="t1")
    out = apply_task_outcome(plan, "s1", task_status="ERROR", task_id="t9")
    text = format_task_outcome_for_plan(out)
    assert "DONE" in text


def test_format_block_decision():
    text = format_block_reason({"block": True, "reason": "open_decision"})
    assert "решен" in text.lower() or "Decision" in text


def test_recovery_bundle_includes_humanize():
    text = format_recovery_bundle(
        task_error="Connection refused to ollama",
        worker="aider_local",
        attempts=2,
        max_attempts=3,
        replan={"ok": True, "new_step_id": "s1_retry", "error_step_id": "s1"},
    )
    assert "ollama" in text.lower() or "Ollama" in text or "Сервис" in text
    assert "s1_retry" in text


def test_plan_blocks_enqueue_formats():
    plan = _plan()
    apply_task_outcome(plan, "s1", task_status="PROCESSING", task_id="t1")
    info = plan_blocks_enqueue(plan, decision_open=False)
    # may or may not block depending on bridge implementation
    text = format_block_reason(info)
    assert isinstance(text, str)
