# -*- coding: utf-8 -*-
"""FC-10: history product card lifecycle fields."""
from __future__ import annotations


def test_history_card_has_prompt_and_lifecycle():
    from core.task_result import history_card_lines, history_detail_text

    row = {
        "id": "t-hist-1",
        "message": "добавь docstring в main.py",
        "status": "DONE",
        "metadata": {
            "created_at": "2026-09-15T10:00:00",
            "started_at": "2026-09-15T10:00:05",
            "finished_at": "2026-09-15T10:00:25",
            "attempts": 2,
        },
        "result": {
            "ok": True,
            "worker": "aider_local",
            "latency": 20.0,
            "attempts": 2,
            "files_changed": ["main.py"],
            "change_set": {"files": ["main.py"], "insertions": 5, "deletions": 1},
            "verification": {"passed": True, "summary": "Verify PASS (1/1)"},
            "summary": "docstring added",
        },
    }
    card = history_card_lines(row)
    assert "docstring" in card["prompt"].lower() or "main" in card["prompt"]
    assert "aider" in card["meta"]
    assert "PASS" in card["verify"]
    assert "file" in card["files"].lower()
    assert "+" in card["files"] or "5" in card["files"]
    detail = history_detail_text(row)
    assert "DONE" in detail or "✓" in detail
    assert "aider" in detail.lower() or "Исполнитель" in detail


def test_history_card_error_path():
    from core.task_result import history_card_lines, history_detail_text

    row = {
        "id": "t-err",
        "message": "сломать специально",
        "status": "ERROR",
        "result": {
            "ok": False,
            "worker": "ollama",
            "error": "verify failed: tests",
            "verification": {"passed": False, "reason": "pytest", "summary": "Verify FAIL: pytest"},
        },
    }
    card = history_card_lines(row)
    assert "FAIL" in card["verify"] or card["error"]
    detail = history_detail_text(row)
    assert "ERROR" in detail or "✗" in detail
    assert "verify" in detail.lower() or "Ошибка" in detail or "FAIL" in detail
