# -*- coding: utf-8 -*-
from types import SimpleNamespace


def test_mock_done():
    from core.night_runtime_bridge import mock_execute_fn

    out = mock_execute_fn({"metadata": {"plan_step_id": "s0"}}, mode="done")
    assert out["terminal_state"] == "DONE"
    assert out["verified"] is True


def test_mock_timeout():
    from core.night_runtime_bridge import mock_execute_fn

    out = mock_execute_fn({}, mode="timeout")
    assert out["terminal_state"] == "ERROR"
    assert out["worker_result"]["kind"] == "worker_timeout"


def test_runtime_bridge_with_stub():
    from core.night_runtime_bridge import runtime_execute_fn

    class Stub:
        def process(self, raw):
            return "DONE"

    fn = runtime_execute_fn(Stub())
    out = fn({"message": "x", "metadata": {"night_mode": True}})
    assert out["terminal_state"] == "DONE"
    assert out.get("verified") is True


def test_runtime_bridge_error():
    from core.night_runtime_bridge import runtime_execute_fn

    class Stub:
        def process(self, raw):
            raise RuntimeError("boom")

    out = runtime_execute_fn(Stub())({"message": "x"})
    assert out["terminal_state"] == "ERROR"
    assert "boom" in out["error"]


def test_loop_with_bridge_mock(tmp_path):
    from core.night_mode_controller import run_autonomous_loop, NightSessionConfig
    from core.night_runtime_bridge import make_execute_fn

    plan = SimpleNamespace(steps=[
        SimpleNamespace(id="s0", title="t", status="PENDING"),
        SimpleNamespace(id="s1", title="t2", status="PENDING"),
    ])
    fn = make_execute_fn(mock=True, mock_mode="done")
    res = run_autonomous_loop(
        plan, execute_fn=fn, config=NightSessionConfig(),
        state_dir=tmp_path, resume=False,
    )
    assert len(res.done) == 2


def test_unverified_rejected_by_loop(tmp_path):
    from core.night_mode_controller import run_autonomous_loop, NightSessionConfig
    from core.night_runtime_bridge import make_execute_fn

    plan = SimpleNamespace(steps=[SimpleNamespace(id="s0", title="t", status="PENDING")])
    fn = make_execute_fn(mock=True, mock_mode="unverified_done")
    res = run_autonomous_loop(
        plan, execute_fn=fn, config=NightSessionConfig(),
        state_dir=tmp_path, resume=False,
    )
    assert res.done == []
    assert len(res.errors) == 1
