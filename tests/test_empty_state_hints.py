# -*- coding: utf-8 -*-
from pathlib import Path

def test_queue_history_empty_hints():
    q = Path("ui/queue_panel.py").read_text(encoding="utf-8")
    h = Path("ui/history_panel.py").read_text(encoding="utf-8")
    assert "queue_empty_hint" in q
    assert "history_empty_hint" in h
    assert "AppFacade" in q
