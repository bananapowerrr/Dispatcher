# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from skills.builtin.analysis import analyze_complexity, find_todos, check_syntax
from core.pipeline_e2e import run_pipeline
from core.mock_worker import SUCCESS


def test_analyze_without_radon(tmp_path: Path):
    r = analyze_complexity(root=tmp_path, target=str(tmp_path))
    assert "error" in r or "data" in r


def test_find_todos_via_registry(tmp_path: Path):
    from skills.skills import SkillRegistry
    from skills.tools import ToolRegistry
    (tmp_path / "a.py").write_text("# TODO: later\nx=1\n", encoding="utf-8")
    reg = SkillRegistry(ToolRegistry(project_root=str(tmp_path)))
    todos = reg._find_todos(path=str(tmp_path))
    assert isinstance(todos, list)


def test_pipeline_completes_trace(tmp_path: Path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "demo.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    res = run_pipeline(project_root=proj, bus_root=tmp_path / "bus", scenario=SUCCESS)
    assert res.final_status == "DONE"
