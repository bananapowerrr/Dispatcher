# -*- coding: utf-8 -*-
"""Day-12 offline: multi-project LocalQueue isolation."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path = [p for p in sys.path if Path(p).resolve() not in {ROOT.resolve()}]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.local_queue import (
    enqueue_desktop_task,
    get_local_queue,
    reset_local_queue,
)


def test_queues_isolated_by_root(tmp_path: Path):
    reset_local_queue()
    a = tmp_path / "proj_a"
    b = tmp_path / "proj_b"
    a.mkdir()
    b.mkdir()

    qa = get_local_queue(a)
    qb = get_local_queue(b)
    assert qa is not qb

    id_a = enqueue_desktop_task("task A", project="A", root=a)
    id_b = enqueue_desktop_task("task B", project="B", root=b)
    assert id_a != id_b
    assert qa.size() >= 1
    assert qb.size() >= 1

    claimed_a = qa.claim()
    assert claimed_a is not None
    assert claimed_a.get("id") == id_a
    assert claimed_a.get("message") == "task A"

    # B still waiting
    claimed_b = qb.claim()
    assert claimed_b is not None
    assert claimed_b.get("id") == id_b
    assert claimed_b.get("message") == "task B"


def test_reset_one_root_keeps_other(tmp_path: Path):
    reset_local_queue()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    enqueue_desktop_task("keep", root=b)
    enqueue_desktop_task("drop", root=a)
    reset_local_queue(a)
    # B still has instance with task or spill
    qb = get_local_queue(b)
    assert qb.size() >= 1


def test_same_root_returns_same_instance(tmp_path: Path):
    reset_local_queue()
    p = tmp_path / "one"
    p.mkdir()
    q1 = get_local_queue(p)
    q2 = get_local_queue(p)
    assert q1 is q2
