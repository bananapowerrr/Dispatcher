# -*- coding: utf-8 -*-
from __future__ import annotations


def test_build_evidence_required_keys():
    from core.execution_evidence import build_execution_evidence, REQUIRED_KEYS

    ev = build_execution_evidence(
        task_id="t1",
        worker="aider_local",
        model="qwen2.5-coder:7b",
        attempt=1,
        terminal_state="DONE",
        changed_files=["a.txt"],
        verification={"ok": True},
    )
    for k in REQUIRED_KEYS:
        assert k in ev
    assert ev["terminal_state"] == "DONE"
    assert ev["changed_files"] == ["a.txt"]


def test_worker_cannot_force_done_without_verify():
    from core.execution_evidence import build_execution_evidence, worker_cannot_force_done

    ev = build_execution_evidence(terminal_state="DONE", worker="x")
    assert worker_cannot_force_done(ev, verified=False) is False
    assert worker_cannot_force_done(ev, verified=True) is True


def test_evidence_from_payload_error():
    from core.execution_evidence import evidence_from_task_payload

    payload = {
        "id": "ui-1",
        "attempts": 2,
        "result": {"error": "boom", "worker": "mock"},
        "metadata": {"route_preview": {"worker": "mock", "advisory": True}},
    }
    ev = evidence_from_task_payload(payload, state_folder="errors")
    assert ev["terminal_state"] == "ERROR"
    assert ev["worker"] == "mock"
    assert ev["attempt"] == 2
    assert "boom" in ev.get("error", "")


def test_merge_evidence_into_payload():
    from core.execution_evidence import build_execution_evidence, merge_evidence_into_payload

    base = {"id": "t", "metadata": {"source": "desktop"}}
    ev = build_execution_evidence(task_id="t", terminal_state="DONE", worker="w")
    out = merge_evidence_into_payload(base, ev)
    assert out["metadata"]["source"] == "desktop"
    assert out["metadata"]["execution_evidence"]["worker"] == "w"


def test_runtime_ops_save_contains_evidence_wire():
    """Source contract: _save merges execution_evidence on terminal states."""
    from pathlib import Path

    roots = [
        Path(__file__).resolve().parents[1] / "src" / "core" / "runtime_ops.py",
        Path("/home/workdir/artifacts/src/core/runtime_ops.py"),
    ]
    src = ""
    for p in roots:
        if p.is_file():
            src = p.read_text(encoding="utf-8")
            break
    assert src
    assert "execution_evidence" in src
    assert "evidence_from_task_payload" in src
    assert "merge_evidence_into_payload" in src
