# -*- coding: utf-8 -*-
"""FC-37B Development Advisor tests."""
from __future__ import annotations

from pathlib import Path

from intelligence.development_advisor import (
    advise,
    draft_living_steps,
    format_session_opening,
)
from intelligence.project_analysis import quick_scan


def _proj(tmp: Path) -> Path:
    (tmp / "app.py").write_text("x = 1\n", encoding="utf-8")
    return tmp


def test_advise_empty_project(tmp_path: Path):
    root = _proj(tmp_path)
    adv = advise(root, limit=3, use_index=False)
    assert adv.situation
    assert adv.advice  # git/tests/readme gaps
    text = adv.format_human()
    assert "Что сейчас происходит" in text
    assert "Я бы продолжил" in text


def test_advise_from_report(tmp_path: Path):
    report = quick_scan(_proj(tmp_path), use_index=False)
    adv = advise(report=report, limit=2)
    assert len(adv.advice) <= 2
    assert adv.plan_draft


def test_draft_steps(tmp_path: Path):
    adv = advise(_proj(tmp_path), limit=2, use_index=False)
    steps = draft_living_steps(adv)
    assert steps
    assert steps[0]["meta"]["source"] == "development_advisor"
    assert steps[0]["status"] == "PENDING"


def test_session_opening(tmp_path: Path):
    text = format_session_opening(_proj(tmp_path))
    assert text
    assert "→" in text or "фундамент" in text or "улучшить" in text.lower() or "структура" in text.lower()


def test_mature_project_fewer_gaps(tmp_path: Path):
    root = _proj(tmp_path)
    (root / ".git").mkdir()
    (root / "README.md").write_text("# X\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    adv = advise(root, use_index=False)
    ids = [a.opportunity_id for a in adv.advice]
    assert "init_git" not in ids
    assert "add_readme" not in ids
