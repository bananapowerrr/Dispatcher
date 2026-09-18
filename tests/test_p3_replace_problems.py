# -*- coding: utf-8 -*-
from pathlib import Path
import json
from ui.problems_panel import collect_problems

def test_editor_replace_api_in_source():
    src = Path("ui/editor_panel.py").read_text(encoding="utf-8")
    assert "_replace_one" in src and "_replace_all" in src
    assert "dirty_paths" in src
    assert "Control-h" in src

def test_collect_problems_from_agentbus(tmp_path: Path):
    d = tmp_path / ".agentbus" / "errors"
    d.mkdir(parents=True)
    (d / "t1.json").write_text(json.dumps({
        "id": "t1", "status": "ERROR", "error": "boom", "files": ["a.py"]
    }), encoding="utf-8")
    items = collect_problems(tmp_path)
    assert any(i["message"] == "boom" for i in items)
    assert any(i["file"] == "a.py" for i in items)

def test_main_has_exit_guard():
    src = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert "_request_close" in src
    assert "WM_DELETE_WINDOW" in src
    assert "ProblemsPanel" in src
