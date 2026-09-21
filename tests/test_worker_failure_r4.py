# -*- coding: utf-8 -*-
from types import SimpleNamespace


def test_timeout():
    from core.worker_failure_contract import classify_execution_outcome
    r = SimpleNamespace(ok=False, timed_out=True, loop_error=False,
                        rate_limit_error=False, billing_error=False,
                        error="", stderr="hang")
    o = classify_execution_outcome(r)
    assert o["kind"] == "worker_timeout"
    assert o["switch_backend"] is True
    assert o["event"] == "TIMEOUT"


def test_rate_limit():
    from core.worker_failure_contract import classify_execution_outcome
    r = SimpleNamespace(ok=False, timed_out=False, loop_error=False,
                        rate_limit_error=True, billing_error=False,
                        error="429 rate limit", stderr="")
    o = classify_execution_outcome(r)
    assert o["kind"] == "worker_rate_limit"
    assert o["prefer_local"] is True


def test_worker_ok_verify_fail():
    from core.worker_failure_contract import classify_execution_outcome
    r = SimpleNamespace(ok=True, timed_out=False, loop_error=False,
                        rate_limit_error=False, billing_error=False,
                        error="", stderr="")
    o = classify_execution_outcome(r, verification_ok=False)
    assert o["kind"] == "verification_failed"
    assert o["worker_ok"] is False  # overall not success path
    assert o["switch_backend"] is False  # not infra switch


def test_preflight_unavailable():
    from core.worker_failure_contract import outcome_from_preflight
    o = outcome_from_preflight(False, "ollama not running")
    assert o["kind"] == "worker_unavailable"
    assert o["switch_backend"] is True


def test_network_from_text():
    from core.worker_failure_contract import classify_execution_outcome
    r = SimpleNamespace(ok=False, timed_out=False, loop_error=False,
                        rate_limit_error=False, billing_error=False,
                        error="connection refused", stderr="")
    o = classify_execution_outcome(r)
    assert o["kind"] == "worker_network"


def test_llm_uses_contract():
    from pathlib import Path
    src = Path("/home/workdir/artifacts/src/core/rp_llm.py").read_text(encoding="utf-8")
    assert "worker_failure_contract" in src
    assert "worker_outcome" in src
