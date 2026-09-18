# -*- coding: utf-8 -*-
from pathlib import Path
from app.files_service import FilesService

def test_files_search(tmp_path: Path):
    (tmp_path / "x.py").write_text("alpha beta\ngamma\n", encoding="utf-8")
    hits = FilesService(tmp_path).search("beta")
    assert hits and hits[0]["path"] == "x.py" and hits[0]["line"] == 1

def test_main_terminal_wire():
    src = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert "def _term(" in src
    assert 'self._term("run"' in src or "self._term(\"run\"" in src
    assert 'self._term("dispatcher"' in src or "dispatcher" in src
    assert "SearchPanel" in src
    assert "_open_search" in src

def test_search_panel_exists():
    assert Path("ui/search_panel.py").is_file()
