# -*- coding: utf-8 -*-
from pathlib import Path
from app.agent_service import AgentService
from app import agent_behavior as ab


def test_suggestions_respect_none(tmp_path: Path, monkeypatch):
    (tmp_path / "x.py").write_text("a=1\n", encoding="utf-8")

    class B:
        suggestions = ab.SUGGESTIONS_NONE
        autonomy = ab.AUTONOMY_AUTO

    monkeypatch.setattr(ab, "load_agent_behavior", lambda root=None: B())
    d = AgentService(tmp_path).suggestions()
    assert d["enabled"] is False
    assert d["items"] == []


def test_suggestions_shape(tmp_path: Path, monkeypatch):
    (tmp_path / "x.py").write_text("a=1\n", encoding="utf-8")

    class B:
        suggestions = ab.SUGGESTIONS_IMPORTANT
        autonomy = ab.AUTONOMY_AUTO

    monkeypatch.setattr(ab, "load_agent_behavior", lambda root=None: B())
    d = AgentService(tmp_path).suggestions(limit=3)
    assert "items" in d
    assert "text" in d
    assert d["enabled"] is True
