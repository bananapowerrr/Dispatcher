# -*- coding: utf-8 -*-
from pathlib import Path


def test_retry_no_enqueue():
    from core.recovery_controller import run_recovery

    out = run_recovery({
        "attempts": 0,
        "result": {"error": "connection refused ollama"},
        "metadata": {},
    })
    assert out["enqueued"] is False
    assert out["decision"]["action"] == "retry"
    assert out["hint"] == "existing_reclaim_or_retry_states"


def test_ask_user_max_attempts():
    from core.recovery_controller import run_recovery

    out = run_recovery({
        "attempts": 3,
        "metadata": {"failure_layer": "reclaim_max_attempts", "recoverable": False},
        "result": {"error": "stuck"},
    })
    assert out["enqueued"] is False
    assert out["decision"]["action"] == "ask_user"
    assert out["applied"] is False


def test_replan_applies_plan(tmp_path: Path):
    from intelligence.living_plan import LivingPlan, LivingStep, save_living_plan, load_living_plan
    from core.recovery_controller import run_recovery

    plan = LivingPlan(summary="t")
    plan.steps.append(LivingStep(id="s1", action="fix", status="ERROR", depends_on=[]))
    save_living_plan(tmp_path, plan)
    row = {
        "attempts": 1,
        "message": "fix again",
        "metadata": {
            "failure_layer": "verification",
            "plan_step_id": "s1",
            "recoverable": True,
        },
        "result": {"error": "pytest", "verification": {"ok": False}},
    }
    out = run_recovery(row, project_root=tmp_path, apply_plan=True, save_plan=True)
    assert out["enqueued"] is False
    assert out["decision"]["action"] == "replan"
    if out.get("plan_replan", {}).get("ok"):
        assert out["applied"] is True
        loaded = load_living_plan(tmp_path)
        assert any("retry" in s.id for s in loaded.steps)
        assert any(s.id == "s1" and s.status == "ERROR" for s in loaded.steps)


def test_annotate_row():
    from core.recovery_controller import annotate_row_with_recovery, run_recovery

    row = {"id": "t", "metadata": {}, "result": {"error": "x"}, "attempts": 3}
    out = run_recovery({**row, "metadata": {"failure_layer": "reclaim_max_attempts"}})
    ann = annotate_row_with_recovery(row, out)
    assert "recovery_controller" in ann["metadata"]
    assert ann["metadata"]["recovery_controller"]["enqueued"] is False


def test_finish_task_error_uses_controller():
    src = Path("/home/workdir/artifacts/src/core/runtime_ops.py").read_text(encoding="utf-8")
    assert "recovery_controller" in src
    assert "run_recovery" in src
