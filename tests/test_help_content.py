"""Help dialog content offline."""
from __future__ import annotations

from ui.help_dialog import HELP_RU


def test_help_has_cycle():
    assert "ЦИКЛ" in HELP_RU or "агент" in HELP_RU


def test_help_has_shortcuts():
    assert "Ctrl+K" in HELP_RU
    assert "F8" in HELP_RU
    assert "Alt+1" in HELP_RU


def test_help_has_recipes_and_checklist():
    assert "РЕЦЕПТ" in HELP_RU or "recipes" in HELP_RU.lower()
    assert "Checklist" in HELP_RU or "Checklist" in HELP_RU
