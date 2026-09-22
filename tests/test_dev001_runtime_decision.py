# -*- coding: utf-8 -*-

def test_done_requires_verification():
    from core.runtime_decision import decide_terminal, evidence_snapshot

    snap = evidence_snapshot(task_id="t1", worker="aider", exec_ok=True, attempt=1)
    snap["terminal_state"] = "DONE"
    d = decide_terminal(snap)
    assert d["terminal_state"] == "ERROR"
    assert "contradict" in d["reason"] or d["reason"] == "verification_missing" or d["contradictions"]


def test_done_with_verify_ok():
    from core.runtime_decision import decide_terminal, evidence_snapshot

    snap = evidence_snapshot(
        task_id="t1",
        worker="aider",
        exec_ok=True,
        verification={"ok": True, "passed": True},
    )
    d = decide_terminal(snap)
    assert d["terminal_state"] == "DONE"
    assert d["ok"] is True


def test_contradiction_exec_fail_done():
    from core.runtime_decision import detect_contradictions, decide_terminal

    ev = {
        "terminal_state": "DONE",
        "exec_ok": False,
        "verification": {"ok": True},
    }
    assert "done_but_exec_failed" in detect_contradictions(ev)
    d = decide_terminal(ev)
    assert d["terminal_state"] == "ERROR"


def test_verification_fail_not_done():
    from core.runtime_decision import decide_terminal, evidence_snapshot

    snap = evidence_snapshot(
        exec_ok=True,
        verification={"ok": False, "passed": False, "reason": "pytest"},
    )
    d = decide_terminal(snap)
    assert d["terminal_state"] != "DONE"


def test_retry_when_allowed():
    from core.runtime_decision import decide_terminal, evidence_snapshot

    snap = evidence_snapshot(exec_ok=False, attempt=0, error="timeout", timed_out=True)
    d = decide_terminal(snap, allow_retry=True, max_attempts=3)
    assert d["terminal_state"] == "RETRY"


def test_worker_self_done_blocked():
    from core.runtime_decision import decide_terminal

    d = decide_terminal({
        "exec_ok": True,
        "worker_declared_done": True,
        "verification": {},
        "terminal_state": "DONE",
    })
    assert d["terminal_state"] == "ERROR"


def test_finish_task_source_has_decision():
    from pathlib import Path
    src = Path("/home/workdir/artifacts/src/core/runtime_ops.py").read_text(encoding="utf-8")
    assert "decide_terminal" in src
    assert "runtime_decision" in src
