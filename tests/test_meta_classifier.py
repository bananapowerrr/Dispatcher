# -*- coding: utf-8 -*-
"""Offline tests for meta_classifier (heuristics; ollama optional)."""
from __future__ import annotations

from meta_classifier import (
    classify_task,
    enrich_task_metadata,
    heuristic_complexity,
    heuristic_task_type,
)


def test_heuristic_types() -> None:
    assert heuristic_task_type("Удали unused imports в foo.py") == "cleanup"
    assert heuristic_task_type("Добавь docstring к bar") == "docs"
    assert heuristic_task_type("Разбей функцию process") == "refactor"
    assert heuristic_task_type("fix traceback in login") == "bugfix"


def test_heuristic_complexity_bounds() -> None:
    assert 1 <= heuristic_complexity("typo in readme") <= 2
    assert heuristic_complexity("архитектурный рефакторинг всего модуля", ["a.py"] * 8) >= 4


def test_classify_fallback_without_meta_env(monkeypatch) -> None:
    monkeypatch.delenv("AGENTBUS_META", raising=False)
    r = classify_task({"message": "format imports", "files": ["a.py"]})
    assert r.source == "heuristic"
    assert r.task_type == "cleanup"
    assert 1 <= r.complexity <= 5


def test_enrich_sets_metadata(monkeypatch) -> None:
    monkeypatch.delenv("AGENTBUS_META", raising=False)
    out = enrich_task_metadata({"message": "Добавь type hints к foo", "files": ["x.py"]})
    meta = out["metadata"]
    assert meta["meta_source"] == "heuristic"
    assert meta["task_type"] in ("typing", "general", "feature")
    assert out.get("complexity") == meta.get("complexity")
    # second call uses cache path
    out2 = enrich_task_metadata(out)
    assert out2["metadata"]["meta_source"] in ("cached", "heuristic")


def test_parse_resilience(monkeypatch) -> None:
    """Even with META on, broken ollama must fall back."""
    monkeypatch.setenv("AGENTBUS_META", "1")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")  # closed port
    monkeypatch.setenv("AGENTBUS_META_TIMEOUT", "2")
    r = classify_task({"message": "refactor auth module", "files": ["a.py", "b.py"]})
    assert r.source == "heuristic"
    assert r.task_type in ("refactor", "general")


if __name__ == "__main__":
    test_heuristic_types()
    test_heuristic_complexity_bounds()
    print("test_meta_classifier smoke OK")
