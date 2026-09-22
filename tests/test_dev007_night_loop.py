# -*- coding: utf-8 -*-
from types import SimpleNamespace


def _plan(n=3):
    steps = [
        SimpleNamespace(id=f"s{i}", title=f"step {i}", status="PENDING", description="")
        for i in range(n)
    ]
    return SimpleNamespace(steps=steps)


def test_all_done_serial():
    from intelligence.night_mode_controller import run_autonomous_loop, MAX_PARALLEL_PROJECTS

    assert MAX_PARALLEL_PROJECTS == 1

    def exec_fn(payload):
        return {"terminal_state": "DONE", "verified": True}

    res = run_autonomous_loop(_plan(3), execute_fn=exec_fn)
    assert len(res.done) == 3
    assert res.errors == []
    assert res.stopped_reason == "complete"


def test_error_triggers_recovery_no_enqueue():
    from intelligence.night_mode_controller import run_autonomous_loop

    def exec_fn(payload):
        return {
            "terminal_state": "ERROR",
            "error": "timeout",
            "worker_result": {"kind": "worker_timeout", "status": "timeout"},
            "attempts": 0,
        }

    res = run_autonomous_loop(_plan(1), execute_fn=exec_fn)
    assert len(res.errors) == 1
    assert res.recovery_outcomes
    assert res.recovery_outcomes[0].get("enqueued") is False


def test_ask_user_stops():
    from intelligence.night_mode_controller import run_autonomous_loop, NightSessionConfig

    def exec_fn(payload):
        return {
            "terminal_state": "ERROR",
            "error": "auth failed",
            "worker_result": {"kind": "worker_auth", "status": "failure"},
            "attempts": 5,
        }

    cfg = NightSessionConfig(apply_plan_recovery=False)
    res = run_autonomous_loop(_plan(5), execute_fn=exec_fn, config=cfg)
    # exhausted or auth → ask_user may stop early
    assert res.stopped_reason in ("ask_user", "recovery_stop", "complete")
    assert len(res.task_payloads) >= 1


def test_max_steps():
    from intelligence.night_mode_controller import run_autonomous_loop, NightSessionConfig

    def exec_fn(payload):
        return {"terminal_state": "DONE", "verified": True}

    cfg = NightSessionConfig(max_steps=2)
    res = run_autonomous_loop(_plan(10), execute_fn=exec_fn, config=cfg)
    assert res.steps_processed == 2
    assert res.stopped_reason == "max_steps"


def test_unverified_done_rejected():
    from intelligence.night_mode_controller import run_autonomous_loop

    def exec_fn(payload):
        return {"terminal_state": "DONE", "verified": False}

    res = run_autonomous_loop(_plan(1), execute_fn=exec_fn)
    assert res.done == []
    assert len(res.errors) == 1
