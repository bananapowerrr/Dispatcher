"""analyze() exposes reconcile info."""
from __future__ import annotations

from pathlib import Path

from app.project_workflow import ProjectWorkflow
from app.plan_service import PlanService
from intelligence.living_plan import LivingPlan, LivingStep


def test_analyze_reconciles_orphan_in_progress(tmp_path: Path):
    (tmp_path / ".agentbus").mkdir(parents=True)
    PlanService(str(tmp_path)).save(
        LivingPlan(
            version=1,
            summary="t",
            steps=[LivingStep(id="s1", action="x", status="IN_PROGRESS", meta={})],
        )
    )
    out = ProjectWorkflow(str(tmp_path)).analyze()
    assert "reconcile" in out
    assert "s1" in (out.get("reconcile") or {}).get("demoted_to_pending", [])
    plan = PlanService(str(tmp_path)).load()
    assert str(plan.steps[0].status).upper() == "PENDING"
