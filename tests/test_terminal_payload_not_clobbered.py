# -*- coding: utf-8 -*-
"""Terminal payload must survive the processing→terminal bus move.

finish_task writes the terminal payload via _save(), then calls
bus.move(processing → terminal). FileBus.move does copy2(src, dst), so the
stale processing snapshot overwrites the terminal payload that _save just
wrote. The result is a terminal file carrying status=CLAIMED and a phase
placeholder instead of the real outcome.
"""
from __future__ import annotations

import json
from pathlib import Path


class _Log:
    def write(self, _msg: str) -> None:
        return None


class _Queue:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def terminal(self, task_id, state, error="", attempts=0):
        self.calls.append((task_id, state, error, attempts))

    def finish(self, task_id, worker, state, error="", attempts=0):
        self.calls.append((task_id, state, error, attempts))


def _make_runtime(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from core.bus import FileBus
    from core.local_queue import LocalQueue
    from core import local_queue as lq
    from core.runtime_ops import RuntimeOps
    from core.tasks import Task

    bus = FileBus(tmp_path / "bus", ("desktop",))
    bus.ensure()
    lq._GLOBAL = LocalQueue(spill_dir=tmp_path / ".agentbus" / "desktop_queue")

    rt = RuntimeOps()
    rt.bus = bus
    rt.log = _Log()
    rt.queue = _Queue()
    rt.worker_id = "agentbus-test"
    rt._emit = lambda *a, **k: None
    return rt, Task


def test_terminal_payload_survives_bus_move(tmp_path, monkeypatch):
    rt, Task = _make_runtime(tmp_path, monkeypatch)
    task = Task.from_dict({
        "id": "plan-1-s1",
        "message": "format",
        "channel": "desktop",
        "files": [],
    })

    # processing snapshot written by _set_phase during the run
    rt._set_phase(task, "prepare")

    state = rt.finish_task(task, "ERROR", {"error": "boom"}, error="boom")
    assert state == "ERROR"

    err_file = tmp_path / "bus" / "channels" / "desktop" / "errors" / "plan-1-s1.json"
    data = json.loads(err_file.read_text(encoding="utf-8"))

    assert data["status"] == "ERROR", f"terminal status clobbered: {data['status']}"
    result = data.get("result") or {}
    assert result.get("error") == "boom", f"terminal error lost: {result}"
    assert result.get("phase") is None, f"phase placeholder leaked: {result}"


def test_done_payload_survives_bus_move(tmp_path, monkeypatch):
    rt, Task = _make_runtime(tmp_path, monkeypatch)
    task = Task.from_dict({
        "id": "plan-1-s2",
        "message": "fix",
        "channel": "desktop",
        "files": [],
    })

    rt._set_phase(task, "exec")
    state = rt.finish_task(
        task,
        "DONE",
        {
            "worker": "mock",
            "ok": True,
            "exit_code": 0,
            "verified": True,
            "verification": {"passed": True, "checks": [{"name": "cmd", "passed": True}]},
        },
    )
    assert state == "DONE"

    done_file = tmp_path / "bus" / "channels" / "desktop" / "done" / "plan-1-s2.json"
    data = json.loads(done_file.read_text(encoding="utf-8"))

    assert data["status"] == "DONE", f"terminal status clobbered: {data['status']}"
    result = data.get("result") or {}
    assert result.get("verified") is True, f"verification evidence lost: {result}"
    assert result.get("worker") == "mock", f"worker contract lost: {result}"
