# -*- coding: utf-8 -*-
"""Offline: profile presets used by wizard / popover."""
from pathlib import Path
from app.agent_behavior import apply_profile, load_agent_behavior, list_profiles, PROFILE_BEGINNER

def test_wizard_profiles_available():
    ps = list_profiles()
    assert len(ps) >= 4
    ids = {p["id"] for p in ps}
    assert ids >= {"beginner", "developer", "advanced", "auto"}

def test_beginner_persists(tmp_path: Path, monkeypatch):
    (tmp_path / "config").mkdir()
    monkeypatch.chdir(tmp_path)
    apply_profile(PROFILE_BEGINNER, root=tmp_path)
    b = load_agent_behavior(tmp_path)
    assert b.profile == "beginner"
    assert b.suggestions == "all"
