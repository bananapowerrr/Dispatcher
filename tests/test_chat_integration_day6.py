# -*- coding: utf-8 -*-
"""Day-6 offline integration: Chat display path without CustomTkinter.

Covers:
  PENDING/queued → progress
  PROCESSING → progress
  VERIFYING → progress
  DONE → terminal summary (files + verify)
  ERROR → human error
  incomplete row does not crash
"""
from __future__ import annotations

from ui.chat_task_bridge import (
    format_progress_event,
    format_task_event,
    format_terminal_event,
    should_prefix_role_label,
)
from ui.result_text import extract_result_text
from ui.chat_messages import format_task_chat_block


def test_pending_progress():
    ev = format_progress_event({"status": "PENDING", "id": "t1"})
    assert ev["chat"]
    assert ev["kind"] == "info"


def test_processing_progress_worker():
    ev = format_task_event(
        {
            "status": "PROCESSING",
            "metadata": {"phase": "executing"},
            "result": {"worker": "aider_local"},
        }
    )
    assert "aider_local" in ev["chat"] or "▶" in ev["chat"]
    assert ev["kind"] == "info"


def test_verifying_progress():
    ev = format_task_event(
        {
            "_state": "processing",
            "metadata": {"phase": "verifying"},
            "result": {"worker": "aider_local"},
        }
    )
    assert ev["chat"]
    # Russian or English phase marker
    low = ev["chat"].lower()
    assert "verif" in low or "провер" in low or "▶" in ev["chat"]


def test_done_terminal_files_and_verify():
    row = {
        "status": "DONE",
        "result": {
            "ok": True,
            "worker": "aider_local",
            "files": ["app.py", "tests/test_app.py"],
            "verification": {"ok": True, "summary": "syntax ok"},
        },
    }
    ev = format_terminal_event(row)
    assert ev["kind"] == "done"
    assert "app.py" in ev["chat"]
    assert "Готово" in ev["chat"] or "✓" in ev["chat"]
    # no double prefix needed
    assert should_prefix_role_label(ev["chat"], "done") is False


def test_error_terminal_human():
    row = {
        "status": "ERROR",
        "result": {"ok": False, "error": "Connection refused to ollama", "worker": "aider_local"},
    }
    ev = format_terminal_event(row)
    assert ev["kind"] == "error"
    assert "⚠" in ev["chat"] or "Не выполнено" in ev["chat"] or "Ollama" in ev["chat"] or "ollama" in ev["chat"].lower()


def test_incomplete_row_safe():
    for bad in (None, {}, {"status": ""}, {"foo": 1}):
        ev = format_task_event(bad)  # type: ignore[arg-type]
        assert isinstance(ev["chat"], str)
        assert len(ev["chat"]) >= 1


def test_result_text_and_chat_messages_agree_on_done():
    row = {
        "status": "DONE",
        "result": {"ok": True, "worker": "mock", "files": ["x.py"]},
    }
    a = extract_result_text(row)
    b = format_task_chat_block(row)
    assert "x.py" in a or "Готово" in a
    assert "x.py" in b or "Готово" in b


def test_lifecycle_sequence_strings():
    """Simulated poll sequence: progress then terminal."""
    rows = [
        {"status": "PENDING", "id": "a"},
        {"status": "PROCESSING", "metadata": {"phase": "executing"}, "result": {"worker": "w"}},
        {"status": "PROCESSING", "metadata": {"phase": "verifying"}, "result": {"worker": "w"}},
        {
            "status": "DONE",
            "result": {"ok": True, "worker": "w", "files": ["f.py"], "verification": {"ok": True}},
        },
    ]
    texts = [format_task_event(r)["chat"] for r in rows]
    assert all(texts)
    assert "f.py" in texts[-1] or "Готово" in texts[-1]
