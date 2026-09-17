# -*- coding: utf-8 -*-
from pathlib import Path
from app.changes_service import ChangesService

def test_post_done_actions_shape(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    cs = ChangesService(tmp_path)
    d = cs.post_done_actions()
    assert "actions" in d
    ids = {a["id"] for a in d["actions"]}
    assert ids >= {"review", "continue", "undo"}
    text = cs.format_post_done()
    assert "Review" in text or "Continue" in text
