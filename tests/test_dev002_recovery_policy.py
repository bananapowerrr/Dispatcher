# -*- coding: utf-8 -*-

def test_timeout_retry():
    from core.recovery_policy import decide_with_policy
    d = decide_with_policy(kind="worker_timeout", attempts=0, max_attempts=3)
    assert d["action"] == "retry"
    assert d["next_attempt"] == 1
    assert d["allow_fallback"] is False or d.get("prefer_local") is True


def test_verification_replan_no_fallback():
    from core.recovery_policy import decide_with_policy
    d = decide_with_policy(kind="verification_failed", attempts=0)
    assert d["action"] == "replan"
    assert d.get("allow_fallback") is False


def test_exhausted_ask_user():
    from core.recovery_policy import decide_with_policy
    d = decide_with_policy(kind="worker_timeout", attempts=3, max_attempts=3)
    assert d["action"] == "ask_user"
    assert d["recoverable"] is False


def test_auth_stop_like_ask():
    from core.recovery_policy import decide_with_policy
    d = decide_with_policy(kind="worker_auth", attempts=0)
    assert d["action"] == "ask_user"


def test_security_stop():
    from core.recovery_policy import decide_with_policy
    d = decide_with_policy(kind="security_violation", attempts=0)
    assert d["action"] == "stop"


def test_unavailable_allows_fallback():
    from core.recovery_policy import decide_with_policy
    d = decide_with_policy(kind="worker_unavailable", attempts=0)
    assert d["action"] == "retry"
    assert d.get("allow_fallback") is True


def test_controller_still_no_enqueue():
    from core.recovery_controller import run_recovery
    out = run_recovery({
        "attempts": 0,
        "metadata": {"worker_outcome": {"kind": "worker_timeout"}},
        "result": {"error": "timeout", "timed_out": True},
    })
    assert out["enqueued"] is False
    assert out["decision"]["action"] == "retry"


def test_controller_verify_replan():
    from core.recovery_controller import run_recovery
    out = run_recovery({
        "attempts": 1,
        "metadata": {"worker_outcome": {"kind": "verification_failed"}},
        "result": {"error": "pytest", "verification": {"ok": False}},
    }, apply_plan=False)
    assert out["enqueued"] is False
    assert out["decision"]["action"] in ("replan", "ask_user")
