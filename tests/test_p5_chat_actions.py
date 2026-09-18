# -*- coding: utf-8 -*-
from pathlib import Path

def test_chat_has_continue_and_inline_diff():
    src = Path("ui/chat_panel.py").read_text(encoding="utf-8")
    assert "show_inline_diff" in src
    assert "_show_continue_actions" in src
    assert "_continue_action" in src
    assert "show_inline_diff(str(task_id" in src or "self.show_inline_diff" in src

def test_main_on_continue():
    src = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert "def _on_continue" in src
    assert "self.chat.on_continue" in src
    assert "problems_panel.refresh" in src

def test_problems_open_task():
    src = Path("ui/problems_panel.py").read_text(encoding="utf-8")
    assert "on_open_task" in src
    assert "_on_open_task" in src
