# -*- coding: utf-8 -*-
"""FC-13: retry/reclaim status lines for chat & history."""
from __future__ import annotations

from core.error_ux import format_retry_status, retry_status_from_row
from core.task_result import history_card_lines


def test_format_attempt_line():
    s = format_retry_status(attempts=2, max_attempts=3)
    assert "попытка 2/3" in s


def test_format_reclaim_stuck():
    s = format_retry_status(attempts=2, max_attempts=3, reclaim_reason="stuck_no_heartbeat")
    assert "reclaim" in s.lower() or "зависла" in s


def test_format_max_attempts():
    s = format_retry_status(attempts=3, max_attempts=3, reclaim_reason="stuck_max_attempts")
    assert "исчерпаны" in s or "⛔" in s


def test_format_deferred():
    s = format_retry_status(deferred=True, attempts=1)
    assert "отложена" in s


def test_from_row():
    row = {
        "attempts": 2,
        "status": "processing",
        "metadata": {
            "attempts": 2,
            "reclaim_reason": "stuck_no_heartbeat",
            "consecutive_verify_fails": 1,
            "phase": "verify",
        },
    }
    s = retry_status_from_row(row)
    assert "2" in s
    assert "verify" in s.lower() or "fails" in s or "reclaim" in s.lower() or "зависла" in s


def test_history_card_includes_retry():
    row = {
        "id": "t-r1",
        "message": "fix bug",
        "status": "ERROR",
        "attempts": 3,
        "metadata": {"attempts": 3, "reclaim_reason": "stuck_max_attempts", "max_attempts": 3},
        "result": {"ok": False, "worker": "aider", "error": "verify failed"},
    }
    card = history_card_lines(row)
    assert card.get("retry")
    assert "3" in card["retry"]
