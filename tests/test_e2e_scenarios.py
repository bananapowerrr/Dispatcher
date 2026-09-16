# -*- coding: utf-8 -*-
"""E2E-oriented offline scenarios for smart pipeline layers.

Does not start the full dispatcher loop or call external LLM APIs.
Run: python -m pytest -q test_e2e_scenarios.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_cache_hit(tmp_path: Path) -> None:
    """Put solution once → second get is a hit (no worker needed)."""
    from solution_cache import SolutionCache

    cache_path = tmp_path / "solution_cache.json"
    cache = SolutionCache(cache_path=cache_path, max_entries=50, ttl_seconds=86400)

    class T:
        message = "format imports in util.py"
        files = ["util.py"]
        project = "demo"
        verify = []
        metadata = {}

    task = T()
    assert cache.get(task, project_root=tmp_path) is None

    # simulate DONE after first run
    key = cache.put(
        task,
        {
            "method": "skill",
            "worker": "skill",
            "skill": "format_code",
            "stdout": "ok",
            "summary": "formatted",
        },
        project_root=tmp_path,
        file_snapshots={"util.py": "import os\n"},
    )
    assert key

    hit = cache.get(task, project_root=tmp_path, require_content_match=False)
    assert hit is not None
    assert hit["solution"]["method"] == "skill"
    assert hit.get("file_snapshots", {}).get("util.py") == "import os\n"


def test_skill_hit() -> None:
    """Common RU/EN phrases map to skills, not None (LLM)."""
    from skills import SkillRegistry

    reg = SkillRegistry()
    cases = [
        ("отформатируй код", "format_code"),
        ("format code with black", "format_code"),
        ("почисти импорты", "cleanup_imports"),
        ("remove unused imports", "cleanup_imports"),
        ("найди todo", "find_todos"),
        ("list todos", "find_todos"),
        ("git status", "git_snapshot"),
        ("git snapshot", "git_snapshot"),
        ("покажи зависимости", "list_deps"),
        ("list dependencies", "list_deps"),
        ("search for FooClass", "search_symbol"),
        ("найди где используется BarHelper", "search_symbol"),
    ]
    for msg, expected in cases:
        got = reg.match(msg)
        assert got == expected, f"{msg!r} → {got!r}, want {expected!r}"

    # complex work must NOT take skill path
    assert reg.match("refactor the auth module architecture") is None
    assert reg.match("реализуй новую фичу оплаты") is None


def test_full_cycle_layers_offline(tmp_path: Path) -> None:
    """Cache miss → skill match → (would be LLM) order is coherent."""
    from solution_cache import SolutionCache
    from skills import SkillRegistry
    from metrics import MetricsCollector

    metrics = MetricsCollector()
    cache = SolutionCache(cache_path=tmp_path / "c.json")

    class T:
        message = "отформатируй код"
        files = []
        project = "p"
        verify = []

    task = T()
    # miss
    if cache.get(task) is None:
        metrics.record("cache_miss")
    else:
        metrics.record("cache_hit")

    skill = SkillRegistry().match(task.message)
    if skill:
        metrics.record("skill_hit")
    else:
        metrics.record("skill_miss")
        metrics.record("llm_call")

    rates = metrics.get_hit_rates()
    assert rates["cache_hit_rate"] == 0.0
    assert rates["skill_hit_rate"] == 1.0
    assert skill == "format_code"


def test_lesson_learning(tmp_path: Path) -> None:
    """Failure is stored; similar task gets avoidance warnings."""
    from lesson_learner import LessonLearner

    path = tmp_path / "lessons.json"
    learner = LessonLearner(lessons_path=path, max_lessons=50)
    task = {"message": "fix the bug in auth login"}
    learner.record_failure(task, "SyntaxError: invalid syntax", worker="w1")
    learner.record_failure(task, "SyntaxError: invalid syntax", worker="w1")

    warnings = learner.get_warnings(task)
    assert warnings, "expected non-empty warnings after syntax failures"
    block = learner.format_warnings_block(task)
    assert "ВНИМАНИЕ" in block or warnings[0] in block


def test_metrics_hit_rates() -> None:
    from metrics import MetricsCollector

    m = MetricsCollector()
    m.record("cache_hit")
    m.record("cache_hit")
    m.record("cache_miss")
    m.record("skill_hit")
    m.record("skill_miss")
    m.record("skill_miss")
    m.record("llm_call")
    m.record("llm_call")
    m.record("llm_fail")

    rates = m.get_hit_rates()
    assert rates["cache_hit_rate"] == pytest.approx(2 / 3, rel=1e-3)
    assert rates["skill_hit_rate"] == pytest.approx(1 / 3, rel=1e-3)
    summary = m.get_summary()
    assert summary["counters"]["cache_hit"] == 2
    assert "hit_rates" in summary

    # save_report works
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        out = m.save_report(Path(d) / "metrics_report.json")
        assert Path(out).is_file()


def test_grouper_orders_related() -> None:
    from task_grouper import TaskGrouper

    tasks = [
        {"id": "1", "project": "a", "message": "fix login", "files": ["auth.py"]},
        {"id": "2", "project": "a", "message": "fix logout", "files": ["auth.py", "session.py"]},
        {"id": "3", "project": "b", "message": "add tests", "files": ["test_x.py"]},
    ]
    ordered = TaskGrouper().sort_for_processing(tasks)
    assert len(ordered) == 3
    assert {t["id"] for t in ordered} == {"1", "2", "3"}


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_cache_hit(Path(d))
    test_skill_hit()
    with tempfile.TemporaryDirectory() as d:
        test_full_cycle_layers_offline(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_lesson_learning(Path(d))
    test_metrics_hit_rates()
    test_grouper_orders_related()
    print("test_e2e_scenarios: OK")
