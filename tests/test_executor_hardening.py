# -*- coding: utf-8 -*-
"""P0-1: ExecutorExecutionResult contract — timeout, exit codes, huge pipes (no deadlock)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from core.executor import ExecutionResult, Executor, _clamp_timeout


def test_execution_result_contract():
    r = ExecutionResult(ok=True, code=0, stdout="hi", latency=0.1)
    assert r.success is True
    assert r.exit_code == 0
    assert r.to_dict()["success"] is True

    t = ExecutionResult(ok=False, timed_out=True, error="timeout", latency=1.0)
    assert t.success is False
    assert t.to_dict()["error"] == "timeout"


def test_clamp_timeout_bounds(monkeypatch):
    monkeypatch.setenv("AGENTBUS_EXEC_HARD_CAP", "100")
    assert _clamp_timeout(5) == 15  # min 15
    assert _clamp_timeout(5000) == 100  # hard cap


def test_normal_success(tmp_path: Path):
    ex = Executor()
    r = ex.run_command([sys.executable, "-c", "print('ok')"], cwd=str(tmp_path), timeout=30)
    assert r.success
    assert r.code == 0
    assert "ok" in r.stdout
    assert r.timed_out is False


def test_exit_one(tmp_path: Path):
    ex = Executor()
    r = ex.run_command([sys.executable, "-c", "import sys; sys.exit(1)"], cwd=str(tmp_path), timeout=30)
    assert r.success is False
    assert r.code == 1
    assert r.timed_out is False


def test_timeout(tmp_path: Path):
    ex = Executor()
    t0 = time.monotonic()
    r = ex.run_command(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=str(tmp_path),
        timeout=2,
    )
    elapsed = time.monotonic() - t0
    assert r.timed_out is True
    assert r.success is False
    assert r.error == "timeout" or "тайм-аут" in (r.stderr or "")
    assert elapsed < 25  # must not wait full 30s


def test_huge_stdout_no_deadlock(tmp_path: Path):
    """Pipe buffer must be drained; otherwise write() blocks forever."""
    ex = Executor()
    # ~2MB of lines
    code = "print('x' * 200 + '\\n')\n" * 1  # single statement printing many lines via loop
    code = (
        "for i in range(5000):\n"
        "    print('LINE', i, 'x' * 80)\n"
    )
    r = ex.run_command([sys.executable, "-c", code], cwd=str(tmp_path), timeout=60)
    assert r.timed_out is False
    assert r.loop_error is False
    # may be truncated; must complete without hang
    assert r.code == 0 or r.success
    assert len(r.stdout) > 0 or r.ok


def test_huge_stderr_no_deadlock(tmp_path: Path):
    ex = Executor()
    code = (
        "import sys\n"
        "for i in range(5000):\n"
        "    print('ERR', i, 'y' * 80, file=sys.stderr)\n"
    )
    r = ex.run_command([sys.executable, "-c", code], cwd=str(tmp_path), timeout=60)
    assert r.timed_out is False
    assert r.loop_error is False
    assert r.code == 0 or r.success


def test_empty_output(tmp_path: Path):
    ex = Executor()
    r = ex.run_command([sys.executable, "-c", "pass"], cwd=str(tmp_path), timeout=30)
    assert r.success
    assert (r.stdout or "") == "" or r.stdout.strip() == ""


def test_crash_nonzero(tmp_path: Path):
    ex = Executor()
    r = ex.run_command(
        [sys.executable, "-c", "raise SystemExit('boom')"],
        cwd=str(tmp_path),
        timeout=30,
    )
    # SystemExit with string → exit code 1
    assert r.success is False


def test_missing_executable(tmp_path: Path):
    ex = Executor()
    r = ex.run_command(["/nonexistent/agentbus_bin_xyz"], cwd=str(tmp_path), timeout=10)
    assert r.success is False
    assert "не найден" in (r.stderr or "") or "not found" in (r.stderr or "").lower() or r.stderr
