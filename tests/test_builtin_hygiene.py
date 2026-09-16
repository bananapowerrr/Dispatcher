# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from skills.builtin.hygiene import (
    convert_print_to_logging, strip_trailing_whitespace, count_lines,
)


def test_convert_print(tmp_path: Path):
    f = tmp_path / "a.py"
    f.write_text("print(1)\nprint(2)\n", encoding="utf-8")
    r = convert_print_to_logging(root=tmp_path, files=["a.py"])
    assert r.get("replaced", 0) >= 2
    text = f.read_text(encoding="utf-8")
    assert "logging.info" in text
    assert "import logging" in text


def test_strip_ws(tmp_path: Path):
    f = tmp_path / "b.py"
    f.write_text("x = 1   \n", encoding="utf-8")
    r = strip_trailing_whitespace(root=tmp_path)
    assert r.get("files_fixed", 0) >= 1
    assert f.read_text(encoding="utf-8") == "x = 1\n"


def test_count_lines(tmp_path: Path):
    (tmp_path / "c.py").write_text("# c\n\nx=1\n", encoding="utf-8")
    r = count_lines(root=tmp_path)
    assert r.get("total_lines", 0) >= 3
