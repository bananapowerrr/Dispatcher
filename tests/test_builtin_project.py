# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from skills.builtin.project import generate_requirements, search_symbol


def test_generate_requirements(tmp_path: Path):
    (tmp_path / "m.py").write_text("import requests\nimport os\n", encoding="utf-8")
    r = generate_requirements(root=tmp_path)
    assert r.get("written") is True
    assert any("requests" in p for p in (r.get("packages") or []))


def test_search_symbol_no_pattern(tmp_path: Path):
    r = search_symbol(
        root=tmp_path,
        target=str(tmp_path),
        pattern=None,
        tool_exec=lambda *a, **k: {"success": False},
    )
    assert r.get("error") == "no pattern"


def test_registry_git_snapshot(tmp_path: Path):
    from skills.skills import SkillRegistry
    from skills.tools import ToolRegistry
    reg = SkillRegistry(ToolRegistry(project_root=str(tmp_path)))
    # may fail without git — should not raise
    out = reg._git_snapshot()
    assert isinstance(out, dict)
