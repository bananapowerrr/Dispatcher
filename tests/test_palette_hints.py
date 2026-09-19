"""Palette empty offline."""
from __future__ import annotations

from ui.palette_hints import palette_no_match_text


def test_empty_query():
    t = palette_no_match_text("")
    assert "plan" in t.lower() or "doctor" in t.lower()


def test_no_match():
    t = palette_no_match_text("xyzzy")
    assert "xyzzy" in t
    assert "help" in t.lower() or "plan" in t.lower()
