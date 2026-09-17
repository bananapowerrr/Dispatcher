# -*- coding: utf-8 -*-
from utils.slash_commands import handle_slash

def test_help_mentions_ui_language():
    text = handle_slash("/help", {}) or ""
    assert "?" in text or "почему" in text.lower() or "Undo" in text or "Agent" in text
    assert "/clear" in text

def test_suggest_command():
    # may soft-fail without project — must not crash
    r = handle_slash("/suggest", {"project": ""})
    assert r is not None
