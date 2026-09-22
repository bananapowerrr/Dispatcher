# -*- coding: utf-8 -*-
from pathlib import Path


def test_notify_error_signature_accepts_row():
    src = Path("/home/workdir/artifacts/ui/chat_panel.py").read_text(encoding="utf-8")
    assert "def notify_error" in src
    assert "row:" in src or "row=" in src
    assert "format_error_row_for_chat" in src
    assert "notify_error(tid, detail, row=data)" in src or "row=data" in src


def test_bridge_enriches_decision():
    from ui.chat_recovery_bridge import format_error_row_for_chat

    row = {
        "attempts": 1,
        "metadata": {"worker_outcome": {"kind": "worker_timeout"}},
        "result": {"error": "timeout", "timed_out": True},
    }
    out = format_error_row_for_chat(row)
    assert out.get("chat")
    assert "Recovery" in out["chat"] or "timeout" in out["chat"].lower() or out.get("phase")


def test_rp_context_has_continuity():
    src = Path("/home/workdir/artifacts/src/core/rp_context.py").read_text(encoding="utf-8")
    assert "task_continuity" in src
    assert "merge_prev_failure" in src


def test_task_continuity_importable():
    from intelligence.task_continuity import continuity_for_next_prompt

    block = continuity_for_next_prompt({
        "attempts": 1,
        "result": {
            "error": "pytest failed",
            "verification": {"ok": False, "reason": "assert"},
            "changed_files": ["a.py"],
        },
    })
    assert "PREVIOUS ATTEMPT" in block
