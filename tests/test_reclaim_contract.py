from __future__ import annotations

import json
import os
import time
from pathlib import Path

from core.reclaim import reclaim_stuck


def _write_task(path: Path, *, attempts: int = 0) -> None:
    path.write_text(
        json.dumps(
            {
                "id": "t-reclaim",
                "attempts": attempts,
                "status": "PROCESSING",
                "message": "test",
                "metadata": {"complexity": 1},
            }
        ),
        encoding="utf-8",
    )


def _backdate(path: Path, sec: float = 10_000.0) -> None:
    """Make the task look stale against the real clock (see test_reclaim_evidence)."""
    old = time.time() - sec
    os.utime(path, (old, old))


def test_stuck_task_is_requeued_and_attempt_is_incremented(tmp_path):
    processing = tmp_path / "processing"
    incoming = tmp_path / "incoming"
    errors = tmp_path / "errors"
    processing.mkdir()

    task = processing / "t-reclaim.json"
    _write_task(task, attempts=0)
    _backdate(task)

    moved = []

    def bus_move(channel, src, dst, name):
        moved.append((channel, src, dst, name))
        return True

    results = reclaim_stuck(
        processing_dir=processing,
        incoming_dir=incoming,
        errors_dir=errors,
        channel="desktop",
        bus_move=bus_move,
        max_attempts=3,
        base_sec=60,
        max_sec=60,
        now=time.time(),
    )

    assert results
    assert results[0]["action"] == "REQUEUE"
    assert results[0]["moved"] is True
    assert moved == [("desktop", "processing", "incoming", "t-reclaim.json")]

    raw = json.loads(task.read_text(encoding="utf-8"))
    assert raw["attempts"] == 1
    assert raw["status"] == "PENDING"
    assert raw["metadata"]["reclaim_reason"] == "stuck_no_heartbeat"


def test_max_attempts_goes_to_error(tmp_path):
    processing = tmp_path / "processing"
    incoming = tmp_path / "incoming"
    errors = tmp_path / "errors"
    processing.mkdir()

    task = processing / "t-reclaim.json"
    _write_task(task, attempts=3)
    _backdate(task)

    moved = []

    def bus_move(channel, src, dst, name):
        moved.append((channel, src, dst, name))
        return True

    results = reclaim_stuck(
        processing_dir=processing,
        incoming_dir=incoming,
        errors_dir=errors,
        channel="desktop",
        bus_move=bus_move,
        max_attempts=3,
        base_sec=60,
        max_sec=60,
        now=time.time(),
    )

    assert results[0]["action"] == "ERROR"
    assert results[0]["moved"] is True
    assert moved[0][2] == "errors"

    raw = json.loads(task.read_text(encoding="utf-8"))
    assert raw["status"] == "ERROR"
    assert raw["metadata"]["reclaim_reason"] == "stuck_max_attempts"


def test_lease_sidecar_is_not_treated_as_task(tmp_path):
    processing = tmp_path / "processing"
    incoming = tmp_path / "incoming"
    errors = tmp_path / "errors"
    processing.mkdir()

    lease = processing / "t-reclaim.lease.json"
    lease.write_text("{}", encoding="utf-8")

    results = reclaim_stuck(
        processing_dir=processing,
        incoming_dir=incoming,
        errors_dir=errors,
        channel="desktop",
        bus_move=lambda *args: True,
        base_sec=60,
        max_sec=60,
        now=10_000,
    )

    assert results == []


def test_recent_lease_heartbeat_prevents_reclaim(tmp_path):
    processing = tmp_path / "processing"
    incoming = tmp_path / "incoming"
    errors = tmp_path / "errors"
    processing.mkdir()

    task = processing / "t-reclaim.json"
    _write_task(task, attempts=0)
    lease = processing / "t-reclaim.lease.json"
    lease.write_text(json.dumps({"last_heartbeat": time.time(), "attempts": 0}), encoding="utf-8")

    results = reclaim_stuck(
        processing_dir=processing,
        incoming_dir=incoming,
        errors_dir=errors,
        channel="desktop",
        bus_move=lambda *args: True,
        base_sec=60,
        max_sec=60,
        now=time.time(),
    )

    assert results == []
