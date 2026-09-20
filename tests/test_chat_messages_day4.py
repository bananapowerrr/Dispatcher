# -*- coding: utf-8 -*-
"""Day-4 offline: chat message formatting."""
from __future__ import annotations

from ui.chat_messages import (
    format_phase_footer,
    format_progress_for_chat,
    format_task_chat_block,
    format_terminal_for_chat,
)
from ui.result_text import extract_result_text


def test_progress_processing():
    row = {
        "status": "PROCESSING",
        "metadata": {"phase": "verifying"},
        "result": {"worker": "aider_local"},
    }
    line = format_progress_for_chat(row)
    assert "aider_local" in line
    assert "▶" in line or "Проверяю" in line or "verif" in line.lower()


def test_done_block_lists_files():
    row = {
        "status": "DONE",
        "result": {
            "ok": True,
            "worker": "aider_local",
            "files": ["test_aider.txt"],
            "verification": {"ok": True, "summary": "syntax ok"},
        },
    }
    block = format_terminal_for_chat(row)
    assert "Готово" in block or "✓" in block
    assert "test_aider.txt" in block


def test_error_block_human():
    row = {
        "status": "ERROR",
        "result": {
            "ok": False,
            "worker": "aider_local",
            "error": "Connection refused to ollama",
        },
    }
    block = format_terminal_for_chat(row)
    assert "⚠" in block or "Не выполнено" in block or "Ollama" in block


def test_task_chat_block_routes():
    assert "▶" in format_task_chat_block({"status": "CLAIMED", "result": {"worker": "x"}}) or "x" in format_task_chat_block(
        {"status": "CLAIMED", "result": {"worker": "x"}}
    )
    done = format_task_chat_block({"status": "DONE", "result": {"ok": True, "files": ["a.py"]}})
    assert "a.py" in done or "Готово" in done


def test_extract_result_uses_chat_for_done():
    text = extract_result_text(
        {
            "status": "DONE",
            "result": {"ok": True, "worker": "aider_local", "files": ["f.py"]},
        }
    )
    assert len(text) > 3


def test_phase_footer():
    s = format_phase_footer("verify", worker="aider_local")
    assert "aider_local" in s
