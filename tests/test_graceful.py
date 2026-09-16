# -*- coding: utf-8 -*-
"""Offline graceful-degradation tests (no LLM, no network)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_meta_unavailable_falls_back_to_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Если ollama meta недоступна — heuristic, не exception."""
    import meta_classifier as mc

    monkeypatch.setenv("AGENTBUS_META", "1")
    monkeypatch.setattr(mc, "_meta_enabled", lambda: True)

    def boom(*_a, **_k):
        raise ConnectionError("ollama down")

    monkeypatch.setattr(mc, "_ollama_chat", boom)
    result = mc.classify_task({"message": "исправь опечатку в readme", "files": ["README.md"]})
    assert result is not None
    assert result.source in ("heuristic", "cached", "ollama")
    # when ollama fails should be heuristic
    assert result.source == "heuristic"
    assert 1 <= int(result.complexity) <= 5


def test_cache_corrupted_skips_to_worker(tmp_path: Path) -> None:
    """Повреждённый cache file не роняет get()."""
    from solution_cache import SolutionCache

    bad = tmp_path / "solution_cache.json"
    bad.write_text("{not-json", encoding="utf-8")
    cache = SolutionCache(cache_path=str(bad))
    task = SimpleNamespace(message="x", files=[], project="p", verify=[])
    assert cache.get(task) is None
    # put still works (rebuilds structure)
    cache.put(task, solution={"ok": True})
    assert cache.get(task, require_content_match=False) is not None


def test_alerts_high_error_rate() -> None:
    from alerts import AlertManager

    am = AlertManager(error_rate_threshold=0.5, cooldown_sec=0)
    fired = am.check_from_metrics(
        {"task_count": 20, "error_count": 12, "hit_rates": {"cache_total": 0, "cache_hit_rate": 0}}
    )
    assert any(a.alert_type == "HIGH_ERROR_RATE" for a in fired)


def test_alerts_cache_ineffective() -> None:
    from alerts import AlertManager

    am = AlertManager(cache_hit_floor=0.1, cooldown_sec=0)
    fired = am.check_from_metrics(
        {
            "task_count": 5,
            "error_count": 0,
            "hit_rates": {"cache_total": 20, "cache_hit_rate": 0.05},
        }
    )
    assert any(a.alert_type == "CACHE_INEFFECTIVE" for a in fired)


def test_alerts_queue_depth() -> None:
    from alerts import AlertManager

    am = AlertManager(queue_depth_limit=10, cooldown_sec=0)
    fired = am.check_queue({"incoming": 50, "processing": 0})
    assert any(a.alert_type == "QUEUE_DEPTH" for a in fired)


def test_ttl_cache_expires() -> None:
    from performance import TTLCache
    import time

    c: TTLCache[str] = TTLCache(maxsize=8, ttl=0.05)
    c.set("a", "v")
    assert c.get("a") == "v"
    time.sleep(0.07)
    assert c.get("a") is None


def test_cached_with_ttl_decorator() -> None:
    from performance import cached_with_ttl

    calls = {"n": 0}

    @cached_with_ttl(ttl=60, maxsize=8)
    def compute(x: int) -> int:
        calls["n"] += 1
        return x * 2

    assert compute(3) == 6
    assert compute(3) == 6
    assert calls["n"] == 1


def test_router_task_complexity_from_meta() -> None:
    from router import task_complexity

    assert task_complexity({"message": "x", "metadata": {"complexity": 5}}) == 5
    assert 1 <= task_complexity({"message": "hi", "files": []}) <= 5
