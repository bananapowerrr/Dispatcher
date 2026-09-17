# -*- coding: utf-8 -*-
from pathlib import Path

from app.project_workflow import ProjectWorkflow


def test_run_preview(tmp_path: Path):
    (tmp_path / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    wf = ProjectWorkflow(tmp_path)
    d = wf.run_preview(limit=3)
    assert "analysis" in d
    assert "advice" in d
    assert "plan" in d
    text = wf.format_preview(limit=3)
    assert "workflow" in text.lower() or "Status" in text or "Advice" in text


def test_build_plan_no_persist(tmp_path: Path):
    (tmp_path / "x.py").write_text("a=1\n", encoding="utf-8")
    plan = ProjectWorkflow(tmp_path).build_plan_from_advice(limit=2, persist=False)
    assert "steps" in plan
    # steps may be empty if advisor fails soft — still structured
    assert isinstance(plan["steps"], list)


def test_analyze_shape(tmp_path: Path):
    (tmp_path / "x.py").write_text("a=1\n", encoding="utf-8")
    a = ProjectWorkflow(tmp_path).analyze()
    assert a.get("project")
    assert "health" in a
