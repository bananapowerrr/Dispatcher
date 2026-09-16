# -*- coding: utf-8 -*-
from project_lock import ProjectLock


def test_same_project_blocked():
    lock = ProjectLock(max_global=3)
    assert lock.acquire("Alpha", "t1")
    assert not lock.acquire("Alpha", "t2")
    assert not lock.can_run("alpha")
    lock.release("Alpha")
    assert lock.acquire("alpha", "t3")


def test_different_projects_ok():
    lock = ProjectLock(max_global=2)
    assert lock.acquire("A", "1")
    assert lock.acquire("B", "2")
    assert not lock.acquire("C", "3")
    lock.release("A")
    assert lock.acquire("C", "3")


def test_snapshot():
    lock = ProjectLock(max_global=2)
    lock.acquire("P", "tid")
    snap = lock.snapshot()
    assert len(snap) == 1
    assert snap[0]["project"] == "P"
    assert snap[0]["task_id"] == "tid"
