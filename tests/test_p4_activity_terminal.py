# -*- coding: utf-8 -*-
from pathlib import Path

def test_activity_bar_items():
    from ui.activity_bar import DEFAULT_ITEMS
    ids = [x[0] for x in DEFAULT_ITEMS]
    assert "explorer" in ids and "plan" in ids and "problems" in ids

def test_main_wires_activity_and_terminal():
    src = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert "ActivityBar" in src
    assert "TerminalPanel" in src
    assert "_on_activity_select" in src
    assert "problems_panel" in src  # in refresh list
    assert "terminal_panel" in src

def test_refresh_includes_problems_plan():
    src = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert '"problems_panel"' in src or "'problems_panel'" in src
    assert '"plan_panel"' in src or "'plan_panel'" in src
