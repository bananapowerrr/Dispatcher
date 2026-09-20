# -*- coding: utf-8 -*-
"""Day 14: recovery_ux → chat_recovery_bridge → ERROR chat block."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_format_recovery_for_chat_basic():
    from ui.chat_recovery_bridge import format_recovery_for_chat

    out = format_recovery_for_chat(task_error="timeout after 30s", worker="aider_local", attempts=2, max_attempts=3)
    assert out["kind"] == "error"
    assert out["chat"]
    assert "phase" in out


def test_format_error_row_with_replan():
    from ui.chat_recovery_bridge import format_error_row_for_chat

    row = {
        "status": "error",
        "result": {"error": "verify failed", "worker": "aider_local"},
        "metadata": {
            "attempts": 1,
            "max_attempts": 3,
            "replan": {
                "ok": True,
                "error_step_id": "s1",
                "new_step_id": "s1_retry",
            },
            "plan_outcome": {
                "ok": True,
                "step_id": "s1",
                "old_status": "IN_PROGRESS",
                "new_status": "ERROR",
            },
        },
    }
    out = format_error_row_for_chat(row)
    assert out["kind"] == "error"
    chat = out["chat"]
    # recovery_ux formats replan / outcome in Russian markers
    assert "↻" in chat or "Replan" in chat or "s1_retry" in chat or "ERROR" in chat


def test_format_error_row_with_block():
    from ui.chat_recovery_bridge import format_error_row_for_chat

    row = {
        "status": "error",
        "error": "blocked",
        "metadata": {"block": {"block": True, "reason": "decision pending"}},
    }
    out = format_error_row_for_chat(row)
    assert "⏸" in out["chat"] or "реш" in out["chat"].lower() or "decision" in out["chat"].lower()


def test_merge_terminal_with_recovery():
    from ui.chat_recovery_bridge import merge_terminal_with_recovery

    t = {"chat": "⚠ verify failed", "phase": "⚠ verify", "kind": "error"}
    r = {"chat": "↻ Replan: step s1\n→ retry s1_r", "phase": "↻ Replan", "kind": "error"}
    m = merge_terminal_with_recovery(t, r)
    assert "verify failed" in m["chat"]
    assert "Replan" in m["chat"] or "↻" in m["chat"]
    assert m["kind"] == "error"


def test_format_terminal_event_enriches_error():
    from ui.chat_task_bridge import format_terminal_event

    row = {
        "status": "error",
        "result": {"error": "boom", "worker": "mock"},
        "metadata": {
            "attempts": 2,
            "replan": {"ok": True, "error_step_id": "a", "new_step_id": "b"},
        },
    }
    out = format_terminal_event(row)
    assert out["kind"] == "error"
    assert out["chat"]


def test_chat_panel_error_path_wires_bridge():
    """Source contract: poll ERROR uses format_error_row_for_chat."""
    roots = [
        Path(__file__).resolve().parents[1] / "ui" / "chat_panel.py",
        Path("/home/workdir/artifacts/chat_panel.py"),
    ]
    src = ""
    for p in roots:
        if p.is_file():
            src = p.read_text(encoding="utf-8")
            break
    assert src, "chat_panel.py not found"
    assert "format_error_row_for_chat" in src
    assert "chat_recovery_bridge" in src


def test_should_prefix_skips_recovery_markers():
    from ui.chat_task_bridge import should_prefix_role_label

    assert should_prefix_role_label("↻ Replan: x", "error") is False
    assert should_prefix_role_label("⏸ План ждёт", "error") is False
    assert should_prefix_role_label("plain fail", "error") is True
