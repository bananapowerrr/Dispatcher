# -*- coding: utf-8 -*-
"""FC-45E/F/G offline contracts."""
from pathlib import Path

from app.tasks_service import TasksService
from app.agent_service import AgentService
from app.workspace_mode import (
    panel_visibility,
    format_mode_help,
    list_modes,
    get_mode,
)


def test_runtime_feedback_idle(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    fb = TasksService(tmp_path).runtime_feedback()
    assert "label" in fb
    assert "status" in fb
    text = TasksService(tmp_path).format_runtime_feedback()
    assert text


def test_explain_context(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    d = AgentService(tmp_path).explain_context("why")
    assert d.get("text")
    assert isinstance(d.get("lines"), list)


def test_panel_visibility_modes():
    modes = {m["id"] for m in list_modes()}
    assert "agent" in modes or get_mode("agent").id == "agent"
    vis_agent = panel_visibility("agent")
    assert vis_agent.get("chat") is True
    vis_code = panel_visibility("code")
    assert isinstance(vis_code, dict)
    help_txt = format_mode_help("agent")
    assert "Mode" in help_txt or "Agent" in help_txt
