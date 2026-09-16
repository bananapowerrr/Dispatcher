# -*- coding: utf-8 -*-
"""Contract: rename/extract skills receive message= and can parse params."""
from __future__ import annotations

from pathlib import Path


def test_try_skill_passes_message_to_rename(tmp_path: Path) -> None:
    """rename_symbol gets message and renames identifier."""
    from skills import SkillRegistry
    from tools import ToolRegistry

    (tmp_path / "a.py").write_text("def old_fn():\n    return 1\n", encoding="utf-8")

    skills = SkillRegistry(ToolRegistry(project_root=str(tmp_path)))
    assert skills.match("переименуй old_fn в new_fn") == "rename_symbol"

    result = skills.execute(
        "rename_symbol",
        path=str(tmp_path),
        message="переименуй old_fn в new_fn",
    )
    assert result.get("success"), result
    payload = result.get("result") or {}
    assert int(payload.get("renamed") or 0) >= 1
    assert "new_fn" in (tmp_path / "a.py").read_text(encoding="utf-8")
    assert "old_fn" not in (tmp_path / "a.py").read_text(encoding="utf-8")


def test_rename_without_message_fails_gracefully(tmp_path: Path) -> None:
    """Without message, skill returns structured error, not TypeError."""
    from skills import SkillRegistry
    from tools import ToolRegistry

    (tmp_path / "a.py").write_text("def old_fn():\n    pass\n", encoding="utf-8")
    skills = SkillRegistry(ToolRegistry(project_root=str(tmp_path)))
    result = skills.execute("rename_symbol", path=str(tmp_path))
    assert result.get("success") is True  # execute catches body errors as success+result
    payload = result.get("result") or {}
    assert int(payload.get("renamed") or 0) == 0
    assert payload.get("error")


def test_extract_function_needs_message(tmp_path: Path) -> None:
    from skills import SkillRegistry
    from tools import ToolRegistry

    src = "def outer():\n    x = 1\n    y = 2\n    return x + y\n"
    (tmp_path / "b.py").write_text(src, encoding="utf-8")
    skills = SkillRegistry(ToolRegistry(project_root=str(tmp_path)))
    assert skills.match("выдели функцию lines 2-3 as helper") == "extract_function"

    result = skills.execute(
        "extract_function",
        path=str(tmp_path / "b.py"),
        files=["b.py"],
        message="extract lines 2-3 as helper",
    )
    assert result.get("success"), result
    payload = result.get("result") or {}
    # ok may be True if extraction succeeded
    assert payload.get("ok") is not False or "helper" in (tmp_path / "b.py").read_text(
        encoding="utf-8"
    )
