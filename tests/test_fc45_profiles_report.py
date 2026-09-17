# -*- coding: utf-8 -*-
from pathlib import Path

from app.agent_behavior import (
    apply_profile,
    list_profiles,
    load_agent_behavior,
    PROFILE_BEGINNER,
    PROFILE_DEVELOPER,
    SUGGESTIONS_ALL,
)
from app.post_step_report import build_post_step_report, format_post_step_report


def test_profiles_list():
    ids = {p["id"] for p in list_profiles()}
    assert "beginner" in ids and "developer" in ids


def test_apply_beginner_profile(tmp_path: Path, monkeypatch):
    (tmp_path / "config").mkdir()
    monkeypatch.chdir(tmp_path)
    b = apply_profile(PROFILE_BEGINNER, root=tmp_path)
    assert b.profile == PROFILE_BEGINNER
    assert b.suggestions == SUGGESTIONS_ALL
    loaded = load_agent_behavior(tmp_path)
    assert loaded.profile == PROFILE_BEGINNER


def test_apply_developer(tmp_path: Path, monkeypatch):
    (tmp_path / "config").mkdir()
    monkeypatch.chdir(tmp_path)
    b = apply_profile(PROFILE_DEVELOPER, root=tmp_path)
    assert b.architecture == "ask"


def test_post_step_report(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    r = build_post_step_report(tmp_path)
    assert "actions" in r
    assert "next_steps" in r
    text = format_post_step_report(r)
    assert "Готово" in text or "завершена" in text or "✓" in text
