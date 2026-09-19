"""ActivityBar badge state without GUI."""
from __future__ import annotations


def test_badge_dict_logic():
    badges: dict[str, int] = {}
    def set_badge(view_id: str, count: int) -> None:
        n = int(count)
        if n <= 0:
            badges.pop(view_id, None)
        else:
            badges[view_id] = min(n, 99)
    set_badge("problems", 3)
    set_badge("plan", 0)
    set_badge("git", 150)
    assert badges["problems"] == 3
    assert "plan" not in badges
    assert badges["git"] == 99
