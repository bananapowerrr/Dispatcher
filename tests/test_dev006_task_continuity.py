# -*- coding: utf-8 -*-

def test_block_contains_instruction():
    from intelligence.task_continuity import build_previous_attempt_block
    text = build_previous_attempt_block(
        attempt=2,
        error="pytest failed on test_x",
        verification={"ok": False, "reason": "assert 1==2"},
        changed_files=["src/core/executor.py"],
        worker="aider_local",
        failure_kind="verification_failed",
    )
    assert "PREVIOUS ATTEMPT #2" in text
    assert "executor.py" in text
    assert "INSTRUCTION" in text
    assert "verification: FAIL" in text


def test_extract_from_payload():
    from intelligence.task_continuity import continuity_for_next_prompt
    payload = {
        "attempts": 1,
        "metadata": {
            "worker_result": {"kind": "worker_timeout", "worker": "aider"},
            "execution_evidence": {"error": "timed out", "attempt": 1},
        },
        "result": {
            "error": "timed out",
            "timed_out": True,
            "changed_files": ["a.py"],
            "verification": {"ok": False},
        },
    }
    block = continuity_for_next_prompt(payload)
    assert "timed out" in block or "timeout" in block.lower() or "PREVIOUS" in block
    assert "a.py" in block


def test_merge_prefers_structured():
    from intelligence.task_continuity import merge_prev_failure
    out = merge_prev_failure(
        "raw error",
        {
            "attempts": 1,
            "result": {
                "error": "verify fail",
                "verification": {"ok": False, "reason": "syntax"},
                "changed_files": ["x.py"],
            },
        },
    )
    assert "PREVIOUS ATTEMPT" in out
    assert "x.py" in out


def test_empty_when_no_history():
    from intelligence.task_continuity import continuity_for_next_prompt
    assert continuity_for_next_prompt({}) == "" or "PREVIOUS" not in continuity_for_next_prompt({"attempts": 0})


def test_rp_context_mentions_continuity():
    from pathlib import Path
    src = Path("/home/workdir/artifacts/src/core/rp_context.py").read_text(encoding="utf-8")
    assert "task_continuity" in src
