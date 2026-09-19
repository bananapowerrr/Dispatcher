"""Plan UI cannot force DONE without task_id."""
from __future__ import annotations

from pathlib import Path

from app.plan_service import PlanService
from intelligence.living_plan import LivingPlan, LivingStep


def test_manual_done_rejected_message(tmp_path: Path):
    (tmp_path / ".agentbus").mkdir(parents=True)
    ps = PlanService(str(tmp_path))
    ps.save(LivingPlan(version=1, summary="t", steps=[
        LivingStep(id="s1", action="x", status="PENDING"),
    ]))
    r = ps.set_step_status("s1", "DONE", note="manual")
    assert r.get("ok") is False
    assert "task_id" in str(r.get("error") or "").lower() or "terminal" in str(r.get("error") or "").lower()
