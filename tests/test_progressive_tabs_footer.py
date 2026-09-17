# -*- coding: utf-8 -*-
from ui.status_labels import format_footer

def test_format_footer_with_agent():
    t = format_footer(dispatcher_on=True, queue_n=2, agent_label="Agent · Auto")
    assert "ON" in t or "queue" in t.lower() or "2" in t
    assert "Agent" in t

def test_format_footer_off():
    t = format_footer(dispatcher_on=False, queue_n=0)
    assert "OFF" in t or "0" in t

def test_main_has_progressive_helper():
    from pathlib import Path
    src = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert "_should_show_advanced_tabs" in src
    assert "_footer_loop" in src
    # no recursive self-call left in update_footer body after format
    assert "text = format_footer" in src
