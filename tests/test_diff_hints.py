"""Diff/history empty hints offline."""
from __future__ import annotations

from ui.diff_hints import diff_empty_hint
from app.facade import AppFacade


def test_diff_empty_no_task():
    t = diff_empty_hint()
    assert "diff" in t.lower() or "Diff" in t
    assert "Apply" in t or "Reject" in t or "apply" in t.lower()


def test_diff_empty_with_task():
    t = diff_empty_hint(task_id="abc123")
    assert "abc123" in t


def test_facade_history_ru():
    msg = AppFacade().empty_message("history")
    assert "Истор" in msg or "history" in msg.lower() or "пуст" in msg.lower()
