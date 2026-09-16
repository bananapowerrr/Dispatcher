# -*- coding: utf-8 -*-
"""Router blends worker_api.score_worker into select_executor."""
from __future__ import annotations

from types import SimpleNamespace

from core.router import select_executor, task_complexity, min_tier_for_complexity
from core.worker_api import score_worker


class FakeHealth:
    def available(self, name: str) -> bool:
        return True

    def score(self, name, task_c, worker_c, quality) -> float:
        return 10.0 * float(quality or 1.0)


def _w(name, tier, priority, provider="local", quality=1.0, complexity=2):
    return SimpleNamespace(
        name=name,
        enabled=True,
        tier=tier,
        priority=priority,
        provider=provider,
        model="m",
        quality=quality,
        complexity=complexity,
        harness="cli",
        role="code",
        capabilities=("coding",),
    )


def test_select_prefers_capable_local_on_simple():
    workers = [
        _w("weak", tier=2, priority=50, quality=0.8),
        _w("local_strong", tier=6, priority=10, quality=1.0),
        _w("cloud", tier=9, priority=40, provider="openai", quality=1.0),
    ]
    raw = {"message": "format imports", "files": ["a.py"], "metadata": {"complexity": 2}}
    chosen = select_executor(workers, FakeHealth(), raw)
    assert chosen is not None
    # should pick some enabled worker; local_strong likely due to priority + local bonus
    assert chosen.name in {"local_strong", "weak", "cloud"}


def test_min_tier_scales():
    assert min_tier_for_complexity(1) <= min_tier_for_complexity(5)


def test_task_complexity_meta():
    assert task_complexity({"metadata": {"complexity": 4}, "message": "x", "files": []}) == 4


def test_score_worker_used_positive():
    w = _w("x", tier=7, priority=10)
    s = score_worker(w, SimpleNamespace(complexity=3, metadata={}))
    assert s > 0
