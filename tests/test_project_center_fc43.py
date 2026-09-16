# -*- coding: utf-8 -*-
"""FC-43 Project Workspace via ProjectService."""
from __future__ import annotations

from pathlib import Path

from app.project_service import ProjectService
from app.tasks_service import TasksService


def test_snapshot_text(tmp_path: Path):
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    ps = ProjectService(tmp_path)
    text = ps.get_snapshot_text(include_capabilities=False)
    assert isinstance(text, str)
    assert len(text) > 0


def test_workspace_summary_shape(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    ps = ProjectService(tmp_path)
    w = ps.workspace_summary()
    assert "snapshot" in w
    assert "queue" in w
    assert "supervisor" in w
    assert "project" in w


def test_audit_text(tmp_path: Path):
    (tmp_path / "main.py").write_text("print(1)\n", encoding="utf-8")
    text = ProjectService(tmp_path).run_audit_text()
    assert isinstance(text, str)


def test_queue_buckets(tmp_path: Path):
    s = TasksService(tmp_path).list_queue_summary()
    assert "buckets" in s
