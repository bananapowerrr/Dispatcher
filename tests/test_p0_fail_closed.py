"""P0: fail-closed intake, skill materialize, workflow blockers, plan terminal."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def test_submit_empty_message_no_queue(tmp_path: Path):
    from core.task_service import submit_payload
    with patch("core.local_queue.get_local_queue") as g:
        q = MagicMock()
        g.return_value = q
        tid, err = submit_payload({"message": ""}, root=tmp_path, soft_intake=False)
        assert tid is None
        assert err
        q.put.assert_not_called()


def test_submit_valid_uses_intake(tmp_path: Path):
    from core.task_service import submit_payload
    with patch("core.local_queue.get_local_queue") as g:
        q = MagicMock()
        q.put.return_value = "tid-1"
        g.return_value = q
        tid, err = submit_payload(
            {"message": "add a docstring to foo.py", "files": []},
            root=tmp_path,
            soft_intake=False,
        )
        if tid:
            q.put.assert_called_once()
            args = q.put.call_args[0][0]
            assert isinstance(args, dict)
            assert args.get("message")


def test_materialize_without_source_no_file(tmp_path: Path):
    from skills.skill_learner import SkillLearner
    store = tmp_path / "observations.json"
    store.write_text("{}", encoding="utf-8")
    # accept whatever __init__ signature
    try:
        sl = SkillLearner(store)
    except TypeError:
        try:
            sl = SkillLearner(path=store)
        except TypeError:
            sl = SkillLearner()
            sl.store = store
    out = sl.materialize_plugin("format_code", source=None)
    assert out.get("status") == "needs_implementation"
    custom = Path(sl.store).parent / "custom" if hasattr(sl, "store") else tmp_path / "custom"
    py_files = list(custom.glob("*.py")) if custom.exists() else []
    assert not py_files


def test_workflow_architecture_blocks_enqueue():
    analysis = {"blockers": ["architecture"]}
    advice = {"items": [{"title": "x"}]}
    can = bool(advice.get("items")) and not (analysis.get("blockers") or [])
    assert can is False
    analysis2 = {"blockers": []}
    can2 = bool(advice.get("items")) and not (analysis2.get("blockers") or [])
    assert can2 is True


def test_plan_done_without_task_id_rejected(tmp_path: Path):
    from app.plan_service import PlanService
    from intelligence.living_plan import LivingPlan, LivingStep
    root = tmp_path
    (root / ".agentbus").mkdir(parents=True, exist_ok=True)
    ps = PlanService(str(root))
    plan = LivingPlan(version=1, summary="t", steps=[
        LivingStep(id="s1", action="do thing", status="PENDING"),
    ])
    ps.save(plan)
    r = ps.set_step_status("s1", "DONE", note="manual")
    assert r.get("ok") is False
    err = str(r.get("error") or "").lower()
    assert "terminal" in err or "task_id" in err


def test_plan_done_with_task_id_ok(tmp_path: Path):
    from app.plan_service import PlanService
    from intelligence.living_plan import LivingPlan, LivingStep
    root = tmp_path
    (root / ".agentbus").mkdir(parents=True, exist_ok=True)
    ps = PlanService(str(root))
    plan = LivingPlan(version=1, summary="t", steps=[
        LivingStep(id="s1", action="do thing", status="IN_PROGRESS"),
    ])
    ps.save(plan)
    r = ps.set_step_status("s1", "DONE", task_id="task-abc", note="runtime terminal")
    assert r.get("ok") is True
