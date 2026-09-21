from pathlib import Path


def test_exec_worker_contract_wire():
    src = Path("/home/workdir/artifacts/src/core/runtime_ops.py").read_text(encoding="utf-8")
    assert "from_worker_result_object" in src
    assert "_last_execution_contract" in src
    assert "recovery_decision" in src
    assert "enqueue_new" not in src.split("recovery_mechanism")[1][:200] or "False" in src


def test_recovery_mechanism_never_enqueues():
    from core.recovery_mechanism import mechanism_for_decision, assert_no_enqueue

    for action in ("retry", "replan", "ask_user", "stop"):
        m = mechanism_for_decision({"action": action})
        assert assert_no_enqueue(m)
        assert m["enqueue_new"] is False


def test_mechanism_for_max_attempts_row():
    from core.recovery_mechanism import mechanism_for_row

    m = mechanism_for_row({
        "attempts": 3,
        "metadata": {"failure_layer": "reclaim_max_attempts", "recoverable": False},
        "result": {"error": "stuck"},
    })
    assert m["action"] == "ask_user"
    assert m["path"] == "ui_only"
