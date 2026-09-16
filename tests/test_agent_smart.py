# -*- coding: utf-8 -*-
"""Tests for project_index, lesson_learner, task_grouper."""
from __future__ import annotations

from pathlib import Path

from project_index import ProjectIndex
from lesson_learner import LessonLearner, classify_task, generate_avoidance
from task_grouper import TaskGrouper


def test_project_index(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        "import os\nclass Foo:\n    def bar(self):\n        return 1\n\ndef helper():\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "other.py").write_text(
        "import os\nfrom mod import Foo\n\ndef use():\n    return Foo()\n",
        encoding="utf-8",
    )
    idx = ProjectIndex(tmp_path)
    n = idx.build()
    assert n >= 2
    assert "mod.py" in idx.index
    assert "Foo" in idx.index["mod.py"]["classes"]
    related = idx.find_related("mod.py")
    assert isinstance(related, list)
    summary = idx.get_module_summary("mod.py")
    assert "Foo" in summary
    ctx = idx.context_snippet(["mod.py"])
    assert "mod.py" in ctx


def test_lesson_learner(tmp_path: Path) -> None:
    path = tmp_path / "lessons.json"
    learner = LessonLearner(lessons_path=path, max_lessons=50)
    task = {"message": "fix the bug in auth"}
    learner.record_failure(task, "SyntaxError: invalid syntax", worker="w1")
    learner.record_failure(task, "SyntaxError: invalid syntax", worker="w1")
    warnings = learner.get_warnings(task)
    assert warnings
    assert any("синтаксис" in w.lower() or "syntax" in w.lower() or "скоб" in w.lower()
               for w in warnings)
    assert classify_task(task) in ("fix", "bugfix")
    assert "тест" in generate_avoidance("AssertionError: fail").lower() or "API" in generate_avoidance("AssertionError: fail")


def test_task_grouper() -> None:
    tasks = [
        {"id": "1", "project": "a", "message": "fix login", "files": ["auth.py"]},
        {"id": "2", "project": "a", "message": "fix logout", "files": ["auth.py", "session.py"]},
        {"id": "3", "project": "b", "message": "add tests", "files": ["test_x.py"]},
        {"id": "4", "project": "a", "message": "format code", "files": ["util.py"]},
    ]
    g = TaskGrouper()
    groups = g.group(tasks)
    assert len(groups) >= 2
    flat = g.sort_for_processing(tasks)
    assert len(flat) == 4
    assert {t["id"] for t in flat} == {"1", "2", "3", "4"}
    summary = g.group_summary(tasks)
    assert summary


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_project_index(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_lesson_learner(Path(d))
    test_task_grouper()
    print("test_agent_smart: OK")
