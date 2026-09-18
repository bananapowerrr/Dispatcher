# -*- coding: utf-8 -*-
from pathlib import Path

def test_enqueue_first_pending_exists():
    from app.project_workflow import ProjectWorkflow
    assert hasattr(ProjectWorkflow, "enqueue_first_pending")
    assert hasattr(ProjectWorkflow, "enqueue_step")

def test_ui_queue_button():
    src = Path("ui/project_center_panel.py").read_text(encoding="utf-8")
    assert "В очередь" in src
    assert "_enqueue_first_step" in src

def test_main_sync_on_enqueue():
    src = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert "step_enqueued" in src
    assert "/enqueue" in src
