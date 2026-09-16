# -*- coding: utf-8 -*-
"""Offline: router prefers role=code for coding tasks."""
from __future__ import annotations

from types import SimpleNamespace

from router import select_executor, task_complexity, _role_bonus


class _Health:
    def available(self, name: str) -> bool:
        return True

    def score(self, name, task_c, worker_c, quality):
        return float(quality)


def _w(name, complexity=2, quality=1.0, role="", enabled=True, provider="ollama", model="x"):
    return SimpleNamespace(
        name=name, complexity=complexity, quality=quality, role=role,
        enabled=enabled, provider=provider, model=model, harness="aider",
        capabilities=(),
    )


def test_task_complexity_from_meta():
    raw = {"message": "x", "files": [], "metadata": {"complexity": 4}}
    assert task_complexity(raw) == 4


def test_role_bonus_code():
    w = _w("aider_local", role="code")
    assert _role_bonus(w, "bugfix", 2) > 0
    w_meta = _w("meta_x", role="meta")
    assert _role_bonus(w_meta, "bugfix", 2) < 0


def test_select_prefers_code_role():
    workers = [
        _w("cloud_heavy", complexity=5, quality=1.0, role="", provider="openrouter"),
        _w("aider_local", complexity=2, quality=1.0, role="code", provider="ollama"),
    ]
    raw = {
        "message": "fix typo in foo.py",
        "files": ["foo.py"],
        "metadata": {"complexity": 2, "task_type": "bugfix"},
    }
    chosen = select_executor(workers, _Health(), raw)
    assert chosen is not None
    assert chosen.name == "aider_local"
