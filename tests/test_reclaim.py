# -*- coding: utf-8 -*-
"""Unit tests for adaptive stuck reclaim (offline)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


def test_compute_stuck_timeout_scales_with_complexity():
    from core.reclaim import compute_stuck_timeout_sec

    t1 = compute_stuck_timeout_sec({"metadata": {"complexity": 1}}, base_sec=300, max_sec=1800)
    t5 = compute_stuck_timeout_sec({"metadata": {"complexity": 5}}, base_sec=300, max_sec=1800)
    assert t5 > t1
    assert t1 >= 60
    assert t5 <= 1800


def test_worker_factor_opencode_longer_than_skill():
    from core.reclaim import compute_stuck_timeout_sec

    local = compute_stuck_timeout_sec(
        {"worker": "ollama_aider", "metadata": {"complexity": 3}},
        base_sec=300,
        max_sec=1800,
    )
    heavy = compute_stuck_timeout_sec(
        {"worker": "opencode_big", "metadata": {"complexity": 3}},
        base_sec=300,
        max_sec=1800,
    )
    assert heavy >= local


def test_reclaim_requeues_stale_under_max_attempts(tmp_path: Path):
    from core.reclaim import reclaim_stuck

    proc = tmp_path / "processing"
    inc = tmp_path / "incoming"
    err = tmp_path / "errors"
    proc.mkdir()
    inc.mkdir()
    err.mkdir()

    tid = "task-stale-1"
    name = f"{tid}.json"
    payload = {
        "id": tid,
        "message": "x",
        "attempts": 1,
        "metadata": {"complexity": 2},
    }
    p = proc / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    # force old mtime
    old = time.time() - 10_000
    import os
    os.utime(p, (old, old))

    results = reclaim_stuck(
        processing_dir=proc,
        incoming_dir=inc,
        errors_dir=err,
        max_attempts=3,
        base_sec=60,
        max_sec=120,
    )
    assert results
    assert results[0]["action"] == "REQUEUE"
    assert results[0]["moved"] is True
    assert (inc / name).is_file() or any(inc.iterdir())
    assert not (proc / name).exists()


def test_reclaim_errors_when_max_attempts(tmp_path: Path):
    from core.reclaim import reclaim_stuck
    import os

    proc = tmp_path / "processing"
    inc = tmp_path / "incoming"
    err = tmp_path / "errors"
    proc.mkdir()
    inc.mkdir()
    err.mkdir()

    tid = "task-dead"
    name = f"{tid}.json"
    payload = {"id": tid, "message": "x", "attempts": 3, "metadata": {"complexity": 2}}
    p = proc / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    old = time.time() - 10_000
    os.utime(p, (old, old))

    results = reclaim_stuck(
        processing_dir=proc,
        incoming_dir=inc,
        errors_dir=err,
        max_attempts=3,
        base_sec=60,
        max_sec=120,
    )
    assert results
    assert results[0]["action"] == "ERROR"
    assert list(err.glob("*.json"))


def test_fresh_task_not_reclaimed(tmp_path: Path):
    from core.reclaim import reclaim_stuck

    proc = tmp_path / "processing"
    inc = tmp_path / "incoming"
    err = tmp_path / "errors"
    proc.mkdir()
    inc.mkdir()
    err.mkdir()
    p = proc / "fresh.json"
    p.write_text(json.dumps({"id": "fresh", "attempts": 0, "metadata": {"complexity": 5}}), encoding="utf-8")

    results = reclaim_stuck(
        processing_dir=proc,
        incoming_dir=inc,
        errors_dir=err,
        max_attempts=3,
        base_sec=300,
        max_sec=1800,
    )
    assert results == []
    assert p.is_file()


def test_write_and_touch_lease(tmp_path: Path):
    from core.reclaim import write_lease, touch_lease, last_active_epoch

    p = tmp_path / "t1.json"
    p.write_text("{}", encoding="utf-8")
    lp = write_lease(p, task_id="t1", worker="aider", complexity=4, attempts=0)
    assert lp is not None and lp.is_file()
    t0 = last_active_epoch(p, {})
    time.sleep(0.05)
    touch_lease(p, phase="execute")
    t1 = last_active_epoch(p, {})
    assert t1 >= t0


def test_fresh_lease_not_reclaimed(tmp_path: Path):
    """Active heartbeat must prevent reclaim (no double execution)."""
    from core.reclaim import reclaim_stuck, write_lease
    import os

    proc = tmp_path / "processing"
    inc = tmp_path / "incoming"
    err = tmp_path / "errors"
    for d in (proc, inc, err):
        d.mkdir()
    tid = "task-live"
    name = f"{tid}.json"
    payload = {"id": tid, "message": "x", "attempts": 0, "metadata": {"complexity": 2}}
    p = proc / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    write_lease(p, task_id=tid, worker="mock", complexity=2, attempts=0)
    # fresh mtime
    now = time.time()
    os.utime(p, (now, now))
    results = reclaim_stuck(
        processing_dir=proc,
        incoming_dir=inc,
        errors_dir=err,
        max_attempts=3,
        base_sec=300,
        max_sec=1800,
    )
    # should not requeue live task
    assert not any(r.get("moved") for r in results)
    assert (proc / name).is_file()


def test_stale_lease_reclaimed(tmp_path: Path):
    from core.reclaim import reclaim_stuck, write_lease
    import os

    proc = tmp_path / "processing"
    inc = tmp_path / "incoming"
    err = tmp_path / "errors"
    for d in (proc, inc, err):
        d.mkdir()
    tid = "task-stale-lease"
    name = f"{tid}.json"
    payload = {"id": tid, "message": "x", "attempts": 0, "metadata": {"complexity": 1}}
    p = proc / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    lp = write_lease(p, task_id=tid, worker="mock", complexity=1, attempts=0)
    old_ts = time.time() - 10_000
    os.utime(p, (old_ts, old_ts))
    if lp and Path(lp).is_file():
        data = json.loads(Path(lp).read_text(encoding="utf-8"))
        data["last_heartbeat"] = old_ts
        Path(lp).write_text(json.dumps(data), encoding="utf-8")
        os.utime(lp, (old_ts, old_ts))
    results = reclaim_stuck(
        processing_dir=proc,
        incoming_dir=inc,
        errors_dir=err,
        max_attempts=3,
        base_sec=60,
        max_sec=120,
    )
    assert any(r.get("action") == "REQUEUE" for r in results)
