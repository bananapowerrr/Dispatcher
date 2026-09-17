# -*- coding: utf-8 -*-
from pathlib import Path

def test_changes_panel_has_undo_method():
    src = Path("ui/changes_panel.py").read_text(encoding="utf-8")
    assert "def _undo_selected" in src
    assert 'text="Undo"' in src or "Undo" in src

def test_getting_started_exists():
    p = Path("docs/GETTING_STARTED.md")
    assert p.is_file()
    t = p.read_text(encoding="utf-8")
    assert "Composer" in t
    assert "DONE" in t

def test_changes_service_undo_api():
    from app.changes_service import ChangesService
    assert hasattr(ChangesService, "undo")
    assert hasattr(ChangesService, "can_undo")
