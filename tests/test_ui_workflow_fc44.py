# -*- coding: utf-8 -*-
"""FC-44: Application API chain used by UI workflow (no toolkit)."""
from __future__ import annotations

from pathlib import Path

from app.agent_service import AgentService
from app.changes_service import ChangesService
from app.files_service import FilesService
from app.project_service import ProjectService
from app.tasks_service import TasksService


def test_editor_to_agent_to_detail_chain(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    fs = FilesService(tmp_path)
    body = fs.read_text("src/main.py")
    assert "def f" in body

    ag = AgentService(tmp_path)
    ag.set_editor_context(active_file="src/main.py", selection="def f():\n    return 1")
    hint = ag.submit_hint("добавь docstring")
    assert hint["active_file"] == "src/main.py"
    assert "src/main.py" in hint["message"]

    # Task detail for unknown id still returns stable shape
    d = TasksService(tmp_path).get_task_detail("ui-demo")
    assert d["id"] == "ui-demo"
    assert "status" in d

    w = ProjectService(tmp_path).workspace_summary()
    assert "snapshot" in w
    assert "queue" in w

    ch = ChangesService(tmp_path).summary()
    assert "count" in ch
    assert "files" in ch


def test_format_detail_and_snapshot_text(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    text = TasksService(tmp_path).format_detail_text("x")
    assert isinstance(text, str)
    snap = ProjectService(tmp_path).get_snapshot_text()
    assert isinstance(snap, str) and len(snap) > 0
