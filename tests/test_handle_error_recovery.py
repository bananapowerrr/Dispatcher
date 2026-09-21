# -*- coding: utf-8 -*-
from pathlib import Path


def test_handle_error_recovery_ask_user_no_enqueue():
    from app.product_surface import handle_error_recovery

    r = handle_error_recovery({
        "attempts": 3,
        "metadata": {"failure_layer": "reclaim_max_attempts"},
        "result": {"error": "stuck"},
    })
    assert r["enqueued"] is False
    assert r["decision"]["action"] == "ask_user"


def test_handle_error_recovery_replan_with_plan(tmp_path: Path):
    from intelligence.living_plan import LivingPlan, LivingStep, save_living_plan
    from app.product_surface import handle_error_recovery

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
        "result": {"error": "verify", "verification": {"ok": False}},
    }
    r = handle_error_recovery(row, project_root=tmp_path, save=True)
    assert r["enqueued"] is False
    assert r["decision"]["action"] == "replan"
    if r.get("replan") and r["replan"].get("ok"):
        assert "PENDING" in r.get("chat_extra", "") or "replan" in r.get("chat_extra", "").lower()
        from intelligence.living_plan import load_living_plan
        loaded = load_living_plan(tmp_path)
        ids = [s.id for s in loaded.steps]
        assert "s1" in ids
        assert any("retry" in i for i in ids)


def test_chat_panel_has_handle_error_recovery():
    src = Path("/home/workdir/artifacts/ui/chat_panel.py").read_text(encoding="utf-8")
    assert "handle_error_recovery" in src
