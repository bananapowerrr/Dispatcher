# -*- coding: utf-8 -*-
"""P0-01: Skill ↔ dispatcher kwargs contract (no dead skills via missing message=)."""
from __future__ import annotations

from pathlib import Path

from skills.skills import SkillRegistry
from skills.tools import ToolRegistry


def _registry(root: Path) -> SkillRegistry:
    tools = ToolRegistry(project_root=str(root))
    return SkillRegistry(tools)


def test_rename_via_execute_needs_message(tmp_path: Path):
    (tmp_path / "a.py").write_text("def old_fn():\n    return 1\n", encoding="utf-8")
    reg = _registry(tmp_path)
    assert reg.match("переименуй old_fn в new_fn") == "rename_symbol"

    # without message → no rename
    bad = reg.execute("rename_symbol", path=str(tmp_path), files=["a.py"])
    assert bad.get("success") is True
    payload = bad.get("result") or {}
    assert int(payload.get("renamed") or 0) == 0
    assert payload.get("error")

    # with message → rename works (dispatcher contract)
    ok = reg.execute(
        "rename_symbol",
        path=str(tmp_path),
        files=["a.py"],
        message="переименуй old_fn в new_fn",
    )
    assert ok.get("success") is True
    payload = ok.get("result") or {}
    assert int(payload.get("renamed") or 0) >= 1
    assert "new_fn" in (tmp_path / "a.py").read_text(encoding="utf-8")


def test_extract_via_execute_needs_message(tmp_path: Path):
    (tmp_path / "b.py").write_text(
        "def host():\n    x = 1\n    y = 2\n    z = x + y\n    return z\n",
        encoding="utf-8",
    )
    reg = _registry(tmp_path)
    # match may or may not fire depending on Russian/English phrasing
    res = reg.execute(
        "extract_function",
        path=str(tmp_path),
        files=["b.py"],
        message="extract lines 2-3 as compute",
    )
    assert res.get("success") is True
    payload = res.get("result") or {}
    # either extracted or clear error about range — not TypeError
    assert "error" not in payload or "TypeError" not in str(payload.get("error"))


def test_try_skill_kwargs_include_message(tmp_path: Path, monkeypatch):
    """Mirror _try_skill kwargs assembly for rename."""
    (tmp_path / "c.py").write_text("def foo():\n    return 0\n", encoding="utf-8")
    message = "rename foo to bar"
    skill_name = "rename_symbol"
    kwargs: dict = {"path": str(tmp_path), "files": ["c.py"], "message": message}
    reg = _registry(tmp_path)
    result = reg.execute(skill_name, **kwargs)
    assert result.get("success")
    assert int((result.get("result") or {}).get("renamed") or 0) >= 1


def test_all_skills_accept_path_kwarg():
    """No skill should TypeError on path= alone (execute filters unexpected)."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "x.py").write_text("x = 1\n", encoding="utf-8")
        reg = _registry(root)
        for name in sorted(reg.skills):
            if name in ("rename_symbol", "extract_function", "search_symbol"):
                continue  # need extra params / may no-op
            out = reg.execute(name, path=str(root))
            assert "success" in out, name
            assert out.get("success") is True or out.get("error"), name
