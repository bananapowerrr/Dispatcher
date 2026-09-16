# -*- coding: utf-8 -*-
from health import HealthRegistry, WorkerState
from project_lock import FileLockSet, ProjectLock


def test_file_lock_blocks_overlap():
    fl = FileLockSet()
    assert fl.acquire(["a.py", "b.py"], "t1")
    assert not fl.acquire(["b.py", "c.py"], "t2")
    assert fl.acquire(["c.py"], "t2")
    fl.release("t1")
    assert fl.acquire(["a.py"], "t3")


def test_file_lock_release_all():
    fl = FileLockSet()
    fl.acquire(["x.py"], "t1")
    fl.release("t1")
    assert fl.can_acquire(["x.py"], "t2")


def test_project_lock_subtask_under_parent():
    pl = ProjectLock(max_global=2)
    assert pl.acquire("proj", "root1")
    assert pl.acquire("proj", "child1", is_subtask=True, parent_id="root1")
    assert not pl.acquire("proj", "other", is_subtask=False)


def test_health_dashboard_rows():
    reg = HealthRegistry(state_file="/tmp/agentbus_test_workers_state.json")
    reg.register("ollama_local", 1)
    reg.success("ollama_local", latency=1.5)
    rows = reg.dashboard_rows()
    assert any(r["worker"] == "ollama_local" for r in rows)
    row = next(r for r in rows if r["worker"] == "ollama_local")
    assert row["status"] in ("HEALTHY", "AVAILABLE", "UNKNOWN", "UNAVAILABLE")
    assert "success_rate" in row
