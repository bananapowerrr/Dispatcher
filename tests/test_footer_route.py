"""Footer click routing heuristics (pure)."""
from __future__ import annotations


def route_footer(text: str) -> str:
    low = (text or "").lower()
    if "⚠" in text or "problem" in low:
        return "problems"
    if "git:" in low:
        return "git"
    if "decision" in low or "📋" in text or "plan:" in low:
        return "plan"
    if "очеред" in low or "queue" in low:
        return "queue"
    return "plan"


def test_route_problems():
    assert route_footer("dispatcher ON · ⚠ 3") == "problems"


def test_route_git():
    assert route_footer("dispatcher ON · git:2") == "git"


def test_route_plan():
    assert route_footer("plan: 2 pending · 📋 1 decision(s)") == "plan"


def test_route_default():
    assert route_footer("dispatcher: ON") == "plan"
