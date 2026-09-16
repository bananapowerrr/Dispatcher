# -*- coding: utf-8 -*-
"""FC-37A Quick Project Analysis tests."""
from __future__ import annotations

from pathlib import Path

from intelligence.project_analysis import (
    apply_analysis_to_state,
    opportunities_as_plan_hints,
    quick_scan,
)
from intelligence.project_state import ProjectState


def _mini_project(tmp: Path, *, with_git: bool = False, with_tests: bool = False) -> Path:
    (tmp / "app.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    (tmp / "pkg").mkdir()
    (tmp / "pkg" / "core.py").write_text("# TODO: improve\nx = 1\n", encoding="utf-8")
    if with_tests:
        (tmp / "tests").mkdir()
        (tmp / "tests" / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    if with_git:
        (tmp / ".git").mkdir()
    return tmp


def test_quick_scan_detects_gaps(tmp_path: Path):
    root = _mini_project(tmp_path)
    report = quick_scan(root, use_index=False)
    assert report.py_files >= 2
    assert report.mode == "quick"
    assert not report.has_readme
    assert not report.has_git
    ids = [o.id for o in report.opportunities]
    assert "add_readme" in ids or "init_git" in ids
    text = report.format_human()
    assert "Анализ" in text or "проект" in text.lower()


def test_quick_scan_with_tests_and_git(tmp_path: Path):
    root = _mini_project(tmp_path, with_git=True, with_tests=True)
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    report = quick_scan(root, use_index=False)
    assert report.has_git
    assert report.has_tests
    assert report.has_readme
    assert report.test_files >= 1


def test_todo_risk_found(tmp_path: Path):
    root = _mini_project(tmp_path)
    report = quick_scan(root, use_index=False)
    assert any("TODO" in r for r in report.risks)


def test_opportunities_to_hints(tmp_path: Path):
    report = quick_scan(_mini_project(tmp_path), use_index=False)
    hints = opportunities_as_plan_hints(report, limit=3)
    assert hints
    assert hints[0]["source"] == "project_analysis"


def test_apply_to_state(tmp_path: Path):
    report = quick_scan(_mini_project(tmp_path), use_index=False)
    state = ProjectState()
    apply_analysis_to_state(report, state)
    assert state.risks


def test_entrypoints(tmp_path: Path):
    root = _mini_project(tmp_path)
    report = quick_scan(root, use_index=False)
    assert "app.py" in report.entrypoints
