# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from skills.builtin.refactor import rename_symbol, extract_function


def test_rename_symbol(tmp_path: Path):
    f = tmp_path / "a.py"
    f.write_text("def old_fn():\n    return 1\n", encoding="utf-8")
    r = rename_symbol(
        root=tmp_path,
        files=["a.py"],
        message="переименуй old_fn в new_fn",
    )
    assert r.get("renamed", 0) >= 1
    assert "new_fn" in f.read_text(encoding="utf-8")


def test_extract_function(tmp_path: Path):
    f = tmp_path / "b.py"
    f.write_text("x = 1\ny = 2\nz = x + y\nprint(z)\n", encoding="utf-8")
    r = extract_function(
        root=tmp_path,
        files=["b.py"],
        message="extract lines 1-3 as compute",
    )
    assert r.get("extracted") is True
    text = f.read_text(encoding="utf-8")
    assert "def compute" in text
