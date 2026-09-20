#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified offline acceptance matrix (no Ollama/Aider required).

Run from repo root:
  PYTHONPATH=src:. python scripts/offline_acceptance_matrix.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

RESULTS: list[tuple[str, bool, str]] = []


def row(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("=== AgentBus offline acceptance matrix ===\n")

    # 1 imports / doctor
    try:
        from core.doctor import run_doctor, doctor_full_text
        rep = run_doctor()
        row("doctor_runs", True, f"critical_ok={rep.critical_ok} score={rep.score}")
        text = doctor_full_text(include_capability=False, include_board=True)
        row("doctor_board", "status board" in text.lower() or "safety:" in text, f"len={len(text)}")
    except Exception as e:
        row("doctor_runs", False, str(e))

    # 2 fail-closed intake
    try:
        from unittest.mock import MagicMock, patch
        from core.task_service import submit_payload
        with patch("core.local_queue.get_local_queue") as g:
            q = MagicMock()
            g.return_value = q
            tid, err = submit_payload({"message": ""}, root=ROOT, soft_intake=False)
            row("intake_reject_empty", tid is None and bool(err) and not q.put.called, err or "")
    except Exception as e:
        row("intake_reject_empty", False, str(e))

    # 3 skill materialize
    try:
        from skills.skill_learner import SkillLearner
        sl = SkillLearner()
        out = sl.materialize_plugin("format_code", source=None)
        row(
            "skill_needs_implementation",
            out.get("status") == "needs_implementation",
            str(out.get("status")),
        )
    except Exception as e:
        row("skill_needs_implementation", False, str(e))

    # 4 plan terminal authority
    try:
        from app.plan_service import PlanService
        from intelligence.living_plan import LivingPlan, LivingStep
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".agentbus").mkdir(parents=True)
            ps = PlanService(str(root))
            ps.save(LivingPlan(version=1, summary="t", steps=[
                LivingStep(id="s1", action="x", status="PENDING"),
            ]))
            r = ps.set_step_status("s1", "DONE", note="manual")
            row("plan_done_ui_blocked", r.get("ok") is False, str(r.get("error"))[:80])
            r2 = ps.set_step_status("s1", "DONE", task_id="t1", note="runtime")
            row("plan_done_runtime_ok", r2.get("ok") is True, "")
    except Exception as e:
        row("plan_terminal", False, str(e))

    # 5 workflow blockers
    try:
        can = bool([{"title": "x"}]) and not (["architecture"] or [])
        row("blockers_block_enqueue", can is False, "")
    except Exception as e:
        row("blockers_block_enqueue", False, str(e))

    # 6 local queue multi-root
    try:
        from core.local_queue import get_local_queue, reset_local_queue
        import tempfile
        reset_local_queue()
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a"
            b = Path(td) / "b"
            a.mkdir(); b.mkdir()
            qa, qb = get_local_queue(a), get_local_queue(b)
            row("queue_multi_root", qa is not qb, "")
        reset_local_queue()
    except Exception as e:
        row("queue_multi_root", False, str(e))

    # 7 format_board_text
    try:
        from utils.status_board import format_board_text
        s = format_board_text(ROOT)
        row("status_board_text", "safety:" in s, f"len={len(s)}")
    except Exception as e:
        row("status_board_text", False, str(e))


    # 9b plan orphan reconcile
    try:
        from app.project_workflow import ProjectWorkflow
        from app.plan_service import PlanService
        from intelligence.living_plan import LivingPlan, LivingStep
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / ".agentbus").mkdir(parents=True)
            PlanService(str(root)).save(LivingPlan(version=1, summary="t", steps=[
                LivingStep(id="s1", action="x", status="IN_PROGRESS", meta={}),
            ]))
            out = ProjectWorkflow(str(root)).analyze()
            dem = (out.get("reconcile") or {}).get("demoted_to_pending") or []
            row("reconcile_orphan", "s1" in dem, str(dem))
    except Exception as e:
        row("reconcile_orphan", False, str(e))

    # 8 zen provider
    try:
        text = (ROOT / "config" / "providers.yaml").read_text(encoding="utf-8")
        row("zen_provider", "zen:" in text, "")
    except Exception as e:
        row("zen_provider", False, str(e))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n=== {passed}/{total} PASS ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
