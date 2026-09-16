# -*- coding: utf-8 -*-
"""FC-41 editor context enriches agent prompt."""
from __future__ import annotations

from pathlib import Path

from app.agent_service import AgentService


def test_enrich_includes_active_file_and_selection():
    ag = AgentService()
    ag.set_editor_context(active_file="src/auth.py", selection="def login():\n    pass")
    out = ag.enrich_prompt("добавь docstring")
    assert "src/auth.py" in out
    assert "def login" in out
    assert "active_file" in out
    assert out.startswith("добавь docstring")


def test_enrich_without_context_is_plain():
    ag = AgentService()
    assert ag.enrich_prompt("hello") == "hello"


def test_submit_hint_shape(tmp_path: Path):
    ag = AgentService(tmp_path)
    ag.set_editor_context(active_file="a.py", selection="x")
    h = ag.submit_hint("fix")
    assert h["active_file"] == "a.py"
    assert h["has_selection"] is True
    assert "a.py" in h["message"]
