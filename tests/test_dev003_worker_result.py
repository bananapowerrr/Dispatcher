# -*- coding: utf-8 -*-
from types import SimpleNamespace


def test_success():
    from core.worker_failure_contract import to_worker_result
    r = SimpleNamespace(ok=True, timed_out=False, loop_error=False,
                        rate_limit_error=False, billing_error=False,
                        error="", stderr="", stdout="ok", code=0, latency=1.0)
    wr = to_worker_result(r, worker="aider_local")
    assert wr["status"] == "success"
    assert wr["ok"] is True
    assert wr["terminal_state"] is None


def test_timeout():
    from core.worker_failure_contract import to_worker_result
    r = SimpleNamespace(ok=False, timed_out=True, loop_error=False,
                        rate_limit_error=False, billing_error=False,
                        error="", stderr="hang", code=None, latency=120)
    wr = to_worker_result(r)
    assert wr["status"] == "timeout"
    assert wr["timed_out"] is True
    assert wr["switch_backend"] is True


def test_unavailable_preflight():
    from core.worker_failure_contract import to_worker_result
    wr = to_worker_result(None, preflight_ok=False, preflight_reason="no ollama")
    assert wr["status"] == "unavailable"


def test_invalid_output_loop():
    from core.worker_failure_contract import to_worker_result
    r = SimpleNamespace(ok=False, timed_out=False, loop_error=True,
                        rate_limit_error=False, billing_error=False,
                        error="loop", stderr="", code=1, latency=2)
    wr = to_worker_result(r)
    assert wr["status"] == "invalid_output"


def test_failure_crash():
    from core.worker_failure_contract import to_worker_result
    r = SimpleNamespace(ok=False, timed_out=False, loop_error=False,
                        rate_limit_error=False, billing_error=False,
                        error="segfault", stderr="boom", code=1, latency=0.1)
    wr = to_worker_result(r)
    assert wr["status"] == "failure"


def test_verify_fail_still_worker_success():
    from core.worker_failure_contract import to_worker_result
    r = SimpleNamespace(ok=True, timed_out=False, loop_error=False,
                        rate_limit_error=False, billing_error=False,
                        error="", stderr="", stdout="diff", code=0, latency=3)
    wr = to_worker_result(r, verification_ok=False)
    assert wr["status"] == "success"
    assert wr["verification_ok"] is False


def test_ops_stores_worker_result():
    from pathlib import Path
    src = Path("/home/workdir/artifacts/src/core/runtime_ops.py").read_text(encoding="utf-8")
    assert "to_worker_result" in src
    assert "_last_worker_result" in src
    assert "worker_result" in src
