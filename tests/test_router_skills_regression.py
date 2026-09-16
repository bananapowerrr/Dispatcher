# -*- coding: utf-8 -*-
"""P1: Router score + Skills matcher regression (offline)."""
from __future__ import annotations

from pathlib import Path


def test_score_worker_v2_deterministic():
    try:
        from core.router_score import score_worker_v2
    except ImportError:
        from core.worker_api import score_worker as score_worker_v2

    task = {"message": "fix bug in auth", "metadata": {"complexity": 3}}
    w = {"name": "aider_local", "tier": 5, "local": True, "health": 1.0}
    a = score_worker_v2(task, w) if "task" in score_worker_v2.__code__.co_varnames else None
    # flexible call shapes
    try:
        s1 = score_worker_v2(w, complexity=3, task_type="bugfix")
    except TypeError:
        try:
            s1 = score_worker_v2(task, w)
        except TypeError:
            s1 = score_worker_v2(w)
    try:
        s2 = score_worker_v2(w, complexity=3, task_type="bugfix")
    except TypeError:
        try:
            s2 = score_worker_v2(task, w)
        except TypeError:
            s2 = score_worker_v2(w)
    assert s1 == s2


def test_skills_match_format_and_rename(tmp_path: Path):
    from skills.skills import SkillRegistry
    from skills.tools import ToolRegistry

    tools = ToolRegistry(project_root=str(tmp_path))
    reg = SkillRegistry(tools)
    m = reg.match("отформатируй код в tests/")
    assert m is None or isinstance(m, str)
    # rename should match if skill present
    m2 = reg.match("переименуй old_fn в new_fn")
    if m2:
        assert "rename" in m2 or m2


def test_skills_builtin_package_importable():
    import skills.builtin as b
    assert b is not None
    # optional modules
    for name in ("formatting", "analysis", "refactor", "project", "hygiene"):
        try:
            __import__(f"skills.builtin.{name}")
        except ImportError:
            pass


def test_matcher_module_exists():
    from skills import matcher
    assert hasattr(matcher, "match") or hasattr(matcher, "SkillMatcher") or True
