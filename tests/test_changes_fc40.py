# -*- coding: utf-8 -*-
"""FC-40 ChangesService tests."""
from __future__ import annotations

from pathlib import Path

from app.changes_service import ChangesService


def test_summary_keys(tmp_path: Path):
    cs = ChangesService(tmp_path)
    s = cs.summary()
    assert "count" in s
    assert "files" in s
    assert isinstance(s["files"], list)


def test_diff_file_no_git(tmp_path: Path):
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    cs = ChangesService(tmp_path)
    # no git repo — empty or comment
    d = cs.diff_file("a.py")
    assert isinstance(d, str)


def test_list_changes_type(tmp_path: Path):
    assert isinstance(ChangesService(tmp_path).list_changes(), list)
