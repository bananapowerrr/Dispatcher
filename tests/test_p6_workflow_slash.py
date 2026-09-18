# -*- coding: utf-8 -*-
from pathlib import Path

def test_slash_commands_in_main():
    src = Path("ui/main_window.py").read_text(encoding="utf-8")
    for cmd in ("/compose", "/audit", "/health", "/plan", "/workflow"):
        assert cmd in src

def test_project_center_advice_to_plan():
    src = Path("ui/project_center_panel.py").read_text(encoding="utf-8")
    assert "_advice_to_plan" in src
    assert "В план" in src

def test_workflow_has_preview():
    src = Path("src/app/project_workflow.py").read_text(encoding="utf-8")
    assert "def format_preview" in src or "def run_preview" in src
