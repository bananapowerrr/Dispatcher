# -*- coding: utf-8 -*-
"""FC-14: WorkerResult contract ↔ TaskResult."""
from __future__ import annotations

from core.worker_api import WorkerResult
from core.task_result import build_task_result


def test_from_exec_execution_like():
    class ER:
        ok = True
        stdout = "done"
        stderr = ""
        latency = 1.5
        timed_out = False
        code = 0
        error = ""
        files_changed = ["a.py"]
        meta = {}

    wr = WorkerResult.from_exec(ER())
    assert wr.ok and wr.files_changed == ["a.py"]
    assert wr.latency == 1.5
    assert wr.exit_code == 0


def test_from_exec_timeout_forces_not_ok():
    wr = WorkerResult.from_exec({"ok": True, "timed_out": True, "stdout": "partial"})
    assert wr.ok is False
    assert wr.timed_out is True
    assert "timeout" in wr.error.lower() or wr.error == "timeout"


def test_from_dict_files_as_dict():
    wr = WorkerResult.from_exec({
        "ok": True,
        "files_changed": {"x.py": "content"},
        "worker": "aider",
        "tokens": 12,
    })
    assert wr.files_changed == ["x.py"]
    assert wr.worker == "aider"
    d = wr.to_dict()
    assert d["files_changed"] == ["x.py"]
    assert d["ok"] is True


def test_to_task_result_fields_and_build():
    wr = WorkerResult(
        ok=True,
        worker="ollama",
        files_changed=["m.py"],
        latency=3.2,
        stdout="ok",
    )
    row = {
        "id": "t-w1",
        "message": "edit m.py",
        "status": "DONE",
        "result": wr.to_task_result_fields(),
    }
    tr = build_task_result(row)
    assert tr.ok is True
    assert tr.worker == "ollama"
    assert "m.py" in tr.changes.files
    assert tr.duration_sec >= 3.0


def test_timeout_row_becomes_error_in_task_result():
    row = {
        "id": "t-to",
        "message": "slow",
        "status": "DONE",
        "result": {"ok": True, "timed_out": True, "worker": "aider", "stdout": "partial"},
    }
    tr = build_task_result(row)
    assert tr.ok is False
    assert "timeout" in (tr.error or "").lower() or tr.status == "ERROR"


def test_config_adapter_sets_name():
    from core.worker_api import ConfigWorkerAdapter

    class W:
        name = "mock_w"
        enabled = True
        tier = 5

    def exec_fn(worker, task, ctx):
        return type("R", (), {"ok": True, "stdout": "x", "stderr": "", "latency": 0.1, "tokens": 1, "meta": {}})()

    ad = ConfigWorkerAdapter(worker=W(), exec_fn=exec_fn)
    wr = ad.execute(type("T", (), {"complexity": 2, "metadata": {}})())
    assert wr.worker == "mock_w"
    assert wr.ok is True
