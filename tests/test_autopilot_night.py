# -*- coding: utf-8 -*-
"""Offline tests for autopilot + night_scheduler."""
from __future__ import annotations

from datetime import datetime, time as dtime
from pathlib import Path

from autopilot import Autopilot, GeneratedTask
from night_scheduler import NightConfig, NightScheduler


def test_autopilot_finds_todo_and_long_fn(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text(
        '''# TODO: implement cache layer
import os
import sys

def huge():
    """doc"""
'''
        + "\n".join(f"    x{i} = {i}" for i in range(60))
        + "\n    return x0\n\ndef no_doc():\n    return 1\n",
        encoding="utf-8",
    )
    ap = Autopilot(tmp_path, long_function_lines=40, max_tasks=50)
    tasks = ap.scan()
    cats = {t.category for t in tasks}
    assert "feature" in cats or any("TODO" in t.message or "todo" in t.message.lower() for t in tasks)
    assert any(t.category == "refactor" for t in tasks) or any("Разбей" in t.message for t in tasks)
    assert any(t.category == "docs" for t in tasks)
    payload = tasks[0].to_bus_payload(channel="gpt")
    assert payload["id"] and payload["message"] and "metadata" in payload


def test_autopilot_write_incoming(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("# FIXME: broken\nx = 1\n", encoding="utf-8")
    bus = tmp_path / "bus"
    ap = Autopilot(tmp_path, max_tasks=5)
    written = ap.write_incoming(bus_root=bus, channel="gpt", limit=3)
    assert written
    assert all(p.is_file() for p in written)
    assert (bus / "channels" / "gpt" / "incoming").is_dir()


def test_night_window_cross_midnight() -> None:
    cfg = NightConfig(start=dtime(22, 0), end=dtime(6, 0), max_tasks_per_night=5, min_complexity=3)
    sched = NightScheduler(cfg)
    night = datetime(2026, 9, 4, 23, 30)
    day = datetime(2026, 9, 4, 12, 0)
    early = datetime(2026, 9, 4, 3, 0)
    assert sched.is_night(night) is True
    assert sched.is_night(early) is True
    assert sched.is_night(day) is False


def test_defer_and_select() -> None:
    cfg = NightConfig(start=dtime(22, 0), end=dtime(6, 0), min_complexity=3, max_tasks_per_night=2)
    sched = NightScheduler(cfg)
    day = datetime(2026, 9, 4, 14, 0)
    hard = {"message": "refactor", "complexity": 5, "priority": 4}
    easy = {"message": "format", "complexity": 1}
    urgent = {"message": "prod down", "complexity": 5, "urgent": True}
    assert sched.should_defer_to_night(hard, now=day) is True
    assert sched.should_defer_to_night(easy, now=day) is False
    assert sched.should_defer_to_night(urgent, now=day) is False
    picked = sched.select_night_tasks([easy, hard, {"id": "x", "complexity": 4, "priority": 5}])
    assert len(picked) <= 2
    assert all(sched._task_complexity(t) >= 3 for t in picked)


def test_morning_report() -> None:
    sched = NightScheduler()
    report = sched.generate_morning_report([
        {"status": "DONE", "message": "add docs", "worker": "skill"},
        {"status": "ERROR", "message": "big change", "error": "TIMEOUT"},
    ])
    assert "Ночной отчёт" in report
    assert "DONE" in report or "Успешно" in report
    assert "TIMEOUT" in report


def test_emit_tasks_sets_complexity_and_source(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text(
        "# TODO: wire night mode\ndef longish():\n"
        + "\n".join(f"    a{i}=1" for i in range(55)),
        encoding="utf-8",
    )
    bus = tmp_path / "bus"
    ap = Autopilot(tmp_path, long_function_lines=40, max_tasks=10)
    written = ap.emit_tasks(bus_root=bus, channel="autopilot", project="demo", limit=5)
    assert written
    import json

    payload = json.loads(written[0].read_text(encoding="utf-8"))
    assert payload["metadata"]["source"] == "autopilot"
    assert "complexity" in payload
    assert payload["complexity"] == payload["metadata"]["complexity"]
    assert Autopilot.map_priority_to_complexity(1) == 2
    assert Autopilot.map_priority_to_complexity(3) == 3
    assert Autopilot.map_priority_to_complexity(5) == 5


def test_filter_for_now_autopilot_hard() -> None:
    cfg = NightConfig(start=dtime(22, 0), end=dtime(6, 0), min_complexity=3)
    sched = NightScheduler(cfg)
    day = datetime(2026, 9, 4, 14, 0)
    hard_auto = {
        "message": "refactor module",
        "complexity": 5,
        "metadata": {"source": "autopilot", "complexity": 5},
    }
    easy = {"message": "fmt", "complexity": 2, "metadata": {"source": "autopilot"}}
    assert sched.filter_for_now(hard_auto, now=day) == "defer_to_night"
    assert sched.filter_for_now(easy, now=day) == "run"
    night = datetime(2026, 9, 4, 23, 0)
    assert sched.filter_for_now(hard_auto, now=night) == "run"


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_autopilot_finds_todo_and_long_fn(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_autopilot_write_incoming(Path(d))
    test_night_window_cross_midnight()
    test_defer_and_select()
    test_morning_report()
    print("test_autopilot_night: OK")
