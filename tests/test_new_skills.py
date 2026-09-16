# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from skills import SkillRegistry
from tools import ToolRegistry


def test_match_new_skills():
    s = SkillRegistry(ToolRegistry(Path(".")))
    assert s.match("отсортируй импорты") == "sort_imports"
    assert s.match("замени print на logging") == "convert_print_to_logging"
    assert s.match("сгенерируй requirements") == "generate_requirements"
    assert s.match("добавь __init__") == "ensure_init_py"
    assert s.match("найди голый open") == "find_bare_io"
    # complex still None
    assert s.match("рефактор архитектуры") is None


def test_convert_print(tmp_path: Path):
    f = tmp_path / "a.py"
    f.write_text("def main():\n    print('hi')\n", encoding="utf-8")
    tools = ToolRegistry(tmp_path)
    s = SkillRegistry(tools)
    r = s.execute("convert_print_to_logging", path=str(tmp_path))
    assert r["success"]
    text = f.read_text(encoding="utf-8")
    assert "logging.info" in text
    assert "import logging" in text


def test_generate_requirements(tmp_path: Path):
    (tmp_path / "m.py").write_text("import requests\nimport os\n", encoding="utf-8")
    s = SkillRegistry(ToolRegistry(tmp_path))
    r = s.execute("generate_requirements", path=str(tmp_path))
    assert r["success"]
    pkgs = (r.get("result") or {}).get("packages") or []
    assert "requests" in pkgs
