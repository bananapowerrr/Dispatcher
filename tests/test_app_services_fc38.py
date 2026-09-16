# -*- coding: utf-8 -*-
"""Application API services tests."""
from __future__ import annotations

from pathlib import Path

from app.agent_service import AgentService
from app.files_service import FilesService
from app.project_service import ProjectService
from app.tasks_service import TasksService
from app.changes_service import ChangesService


def test_files_tree_and_read(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("print(1)\n", encoding="utf-8")
    fs = FilesService(tmp_path)
    tree = fs.tree(max_depth=3)
    assert tree
    text = fs.read_text("src/a.py")
    assert "print" in text
    fs.write_text("src/b.py", "x=2\n")
    assert fs.exists("src/b.py")


def test_files_path_sandbox(tmp_path: Path):
    fs = FilesService(tmp_path)
    try:
        fs.read_text("../outside.py")
        assert False, "should raise"
    except (PermissionError, FileNotFoundError, ValueError):
        pass


def test_project_service_snapshot(tmp_path: Path):
    (tmp_path / "x.py").write_text("a=1\n", encoding="utf-8")
    ps = ProjectService(tmp_path)
    d = ps.get_snapshot()
    assert "status" in d
    assert ps.get_snapshot_text()


def test_agent_enrich():
    ag = AgentService("/tmp")
    ag.set_editor_context(active_file="src/a.py", selection="def f():\n    pass", cursor_line=1)
    msg = ag.enrich_prompt("объясни")
    assert "active_file" in msg
    assert "def f" in msg


def test_tasks_supervisor(tmp_path: Path):
    ts = TasksService(tmp_path)
    st = ts.supervisor_status()
    assert "label" in st
    q = ts.list_queue_summary()
    assert "buckets" in q


def test_changes_summary(tmp_path: Path):
    cs = ChangesService(tmp_path)
    s = cs.summary()
    assert "count" in s
