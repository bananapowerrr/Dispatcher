# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from meta_classifier import classify_task, heuristic_risk, heuristic_suggested_worker
from presets import apply_preset, list_presets, load_preset
from skills import SkillRegistry
from tools import ToolRegistry
from workers import Worker


def test_list_presets():
    names = list_presets()
    assert "local_only" in names
    assert "fast" in names


def test_apply_local_only():
    workers = [
        Worker(name="aider_local", harness="aider", provider="ollama", model="x",
               command=("{aider}",), priority=10, timeout=100, complexity=2),
        Worker(name="opencode", harness="opencode", provider="zen", model="",
               command=("{opencode}",), priority=20, timeout=100, complexity=5),
    ]
    preset = load_preset("local_only")
    assert preset.get("name") == "local_only"
    filtered = apply_preset(workers, preset)
    assert len(filtered) == 1
    assert filtered[0].name == "aider_local"


def test_meta_risk_and_worker():
    r = classify_task({"message": "typo in readme", "files": ["README.md"]})
    assert r.risk_level in ("low", "medium", "high")
    assert r.suggested_worker
    assert heuristic_risk("migrate production db", ["a.py"] * 10, 5) == "high"
    assert heuristic_suggested_worker("cleanup", 2, "low") == "aider_local"


def test_rename_skill(tmp_path: Path):
    f = tmp_path / "m.py"
    f.write_text("def foo():\n    return 1\n\nx = foo()\n", encoding="utf-8")
    s = SkillRegistry(ToolRegistry(tmp_path))
    r = s.execute("rename_symbol", path=str(tmp_path), old_name="foo", new_name="bar")
    assert r["success"]
    text = f.read_text(encoding="utf-8")
    assert "def bar" in text and "foo" not in text
