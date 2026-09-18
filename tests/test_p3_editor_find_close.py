# -*- coding: utf-8 -*-
from pathlib import Path

def test_editor_find_and_confirm_in_source():
    src = Path("ui/editor_panel.py").read_text(encoding="utf-8")
    assert "_show_find" in src
    assert "_find_next" in src
    assert "Control-f" in src
    assert "_confirm_discard" in src
    assert "askyesnocancel" in src
    assert "_goto_line" in src
    assert "soft: still close" not in src
