# -*- coding: utf-8 -*-
from __future__ import annotations

from task_decomposer import TaskDecomposer
from router import min_tier_for_complexity, needs_capacity_shard, max_available_tier
from workers import Worker


class _Health:
    def available(self, name):
        return True


def test_proactive_should_decompose_multi_file():
    d = TaskDecomposer()
    assert d.should_decompose({
        "complexity": 4,
        "files": ["a.py", "b.py"],
        "message": "improve modules",
    })


def test_is_atomic_single_file():
    d = TaskDecomposer()
    assert d.is_atomic({"files": ["a.py"], "message": "fix typo"})
    assert not d.is_atomic({"files": ["a.py", "b.py", "c.py"], "message": "refactor all"})


def test_shard_for_capacity_per_files():
    d = TaskDecomposer()
    subs = d.shard_for_capacity({
        "id": "p1",
        "message": "refactor auth",
        "files": ["a.py", "b.py", "c.py", "d.py"],
        "complexity": 5,
    }, max_complexity=2)
    assert len(subs) >= 2
    assert all(s.estimated_complexity <= 2 for s in subs)
    assert any("[SHARD" in s.message for s in subs)


def test_needs_capacity_shard():
    light = [Worker(name="local", command=("echo",), complexity=2, tier=5, enabled=True)]
    raw = {"message": "big refactor", "files": ["a.py"] * 5, "metadata": {"complexity": 5}}
    assert min_tier_for_complexity(5) == 8
    assert max_available_tier(light, _Health()) == 5
    assert needs_capacity_shard(raw, light, _Health()) is True

    heavy = [Worker(name="cloud", command=("echo",), complexity=5, tier=9, enabled=True)]
    assert needs_capacity_shard(raw, heavy, _Health()) is False
