"""PEV empty placeholder offline."""
from __future__ import annotations

from ui.pev_text import pev_empty_text


def test_pev_empty_mentions_path():
    t = pev_empty_text()
    assert "current_plan.md" in t
    assert "PEV" in t


def test_pev_empty_ru():
    assert "план" in pev_empty_text().lower() or "План" in pev_empty_text()
