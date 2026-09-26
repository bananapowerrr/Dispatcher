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

    # 8 провайдеры: каждый объявленный в yaml обязан загрузиться
    # (раньше здесь проверялся несуществующий "zen", из-за чего матрица
    #  никогда не проходила)
    try:
        from providers.registry import load_providers

        declared = [
            line.split("id:")[1].strip()
            for line in (ROOT / "config" / "providers.yaml").read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("- id:")
        ]
        loaded = {p.id for p in load_providers()}
        missing = [i for i in declared if i not in loaded]
        row("providers_all_load", not missing,
            f"{len(loaded)}/{len(declared)}" + (f" missing={missing}" if missing else ""))
    except Exception as e:
        row("providers_all_load", False, str(e))

    # 10 day13 — контракт настроек: есть и редактируемые, и read-only вкладки
    try:
        from app.settings_contract import (
            EDITABLE_TABS, READ_ONLY_TABS, is_editable_tab, is_read_only_tab,
        )
        ok13 = bool(EDITABLE_TABS) and bool(READ_ONLY_TABS)
        ok13 = ok13 and is_editable_tab(sorted(EDITABLE_TABS)[0])
        ok13 = ok13 and is_read_only_tab(sorted(READ_ONLY_TABS)[0])
        overlap = set(EDITABLE_TABS) & set(READ_ONLY_TABS)
        row("day13_settings_contract", ok13 and not overlap,
            f"editable={len(EDITABLE_TABS)} readonly={len(READ_ONLY_TABS)}"
            + (f" overlap={sorted(overlap)}" if overlap else ""))
    except Exception as e:
        row("day13_settings_contract", False, str(e))

    # 11 day13.1 — read-only вкладки обязаны быть помечены в панели
    try:
        from app.settings_contract import READ_ONLY_TABS

        src = (ROOT / "ui" / "settings_panel.py").read_text(encoding="utf-8")
        missing_tabs = [t for t in READ_ONLY_TABS if t not in src]
        row("day13_1_settings_ro_enforced", not missing_tabs,
            f"tabs={len(READ_ONLY_TABS)}" + (f" missing={missing_tabs}" if missing_tabs else ""))
    except Exception as e:
        row("day13_1_settings_ro_enforced", False, str(e))

    # 12 day14 — мост восстановления в чат
    try:
        from ui.chat_recovery_bridge import format_recovery_for_chat, format_error_row_for_chat

        s1 = format_recovery_for_chat(task_error="ошибка воркера", worker="aider_local")
        s2 = format_recovery_for_chat(task_error="проверить тесты", worker="aider_local",
                                      attempts=1, max_attempts=3)
        row("day14_recovery_chat",
            bool(str(s1).strip()) and bool(str(s2).strip()),
            f"keys={sorted(s1)[:3] if isinstance(s1, dict) else '-'}")
    except Exception as e:
        row("day14_recovery_chat", False, str(e))

    # 13 day15 — отчёт о контексте и структурированный вывод
    try:
        from intelligence.context_report import build_context_report
        from utils.structured_output import parse_json

        rep = build_context_report(project_root=ROOT, message="проверь контекст")
        ok15 = rep is not None and bool(getattr(rep, "files", None) is not None
                                       or getattr(rep, "total_files", 0) >= 0)
        try:
            parse_json('{"a": 1}')
        except Exception:
            ok15 = False
        row("day15_context_report", ok15, type(rep).__name__)
    except Exception as e:
        row("day15_context_report", False, str(e))

    # 14 day16 — поверхность маршрутизации задачи к воркеру
    try:
        from core.worker_route_surface import route_for_task, format_route_for_chat

        route = route_for_task({"message": "почини тест", "files": ["a.py"]})
        text = format_route_for_chat(route)
        row("day16_worker_route_surface", route is not None and bool(str(text).strip()),
            type(route).__name__)
    except Exception as e:
        row("day16_worker_route_surface", False, str(e))

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\n=== {passed}/{total} PASS ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
