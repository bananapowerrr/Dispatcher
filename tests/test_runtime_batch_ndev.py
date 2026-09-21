# -*- coding: utf-8 -*-
from pathlib import Path


def test_lifecycle_touches_worker_phase():
    src = Path("/home/workdir/artifacts/src/core/rp_lifecycle.py").read_text(encoding="utf-8")
    assert 'phase="worker"' in src
    assert "touch_task_lease(task, phase=\"worker\")" in src


def test_rp_llm_touches_exec_phases():
    src = Path("/home/workdir/artifacts/src/core/rp_llm.py").read_text(encoding="utf-8")
    assert 'phase="exec"' in src
    assert 'phase="post_exec"' in src


def test_recovery_decision_max_attempts():
    from core.recovery_decision import decide_recovery, decide_from_task_row

    d = decide_recovery(reclaim_reason="stuck_max_attempts", attempts=3, max_attempts=3)
    assert d["action"] == "ask_user"
    assert d["recoverable"] is False

    d2 = decide_recovery(error="connection refused ollama", attempts=0)
    assert d2["action"] == "retry"

    d3 = decide_from_task_row({
        "attempts": 1,
        "metadata": {"failure_layer": "verification", "recoverable": True},
        "result": {"error": "pytest failed"},
    })
    assert d3["failure_layer"] == "verification"
    assert d3["action"] in ("replan", "ask_user")


def test_worker_execution_normalize():
    from core.worker_execution import normalize_execution_result, from_worker_result_object

    r = normalize_execution_result(ok=True, worker="aider_local", model="qwen", changed_files=["a.py"])
    assert r["ok"] is True and r["worker"] == "aider_local"

    class Fake:
        ok = False
        stdout = ""
        stderr = "boom"
        error = ""
        timed_out = True
        latency = 1.5

    r2 = from_worker_result_object(Fake(), worker="mock")
    assert r2["ok"] is False and r2["timed_out"] is True


def test_rp_verify_touches_verify_phase():
    src = Path("/home/workdir/artifacts/src/core/rp_verify.py").read_text(encoding="utf-8")
    assert 'phase="verify"' in src
    assert "touch_task_lease" in src
