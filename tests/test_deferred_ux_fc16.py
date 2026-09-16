# -*- coding: utf-8 -*-
"""FC-16: deferred status UX."""
from __future__ import annotations

import time

from core.error_ux import format_retry_status, retry_status_from_row, format_deferred_banner
from core.task_result import history_card_lines


def test_deferred_quota_message():
    s = format_retry_status(deferred=True, deferred_reason="DEFERRED_QUOTA", wake_at=90)
    assert "отложена" in s
    assert "квот" in s.lower() or "воркер" in s.lower()
    assert "мин" in s or "с" in s


def test_deferred_busy():
    s = format_retry_status(deferred=True, deferred_reason="PROJECT_BUSY", wake_at=30)
    assert "занят" in s


def test_from_row_with_wake_epoch():
    row = {
        "_state": "deferred",
        "status": "deferred",
        "attempts": 1,
        "result": {
            "error": "DEFERRED_QUOTA",
            "category": "RATE_LIMIT",
            "wake_epoch": time.time() + 120,
            "wake_at": 120,
        },
    }
    s = retry_status_from_row(row)
    assert "отложена" in s
    banner = format_deferred_banner(row)
    assert "⏳" in banner or "отложен" in banner.lower()


def test_history_card_retry_for_deferred():
    row = {
        "id": "t-def",
        "message": "большая задача",
        "_state": "deferred",
        "status": "deferred",
        "result": {"error": "DEFERRED_QUOTA", "wake_at": 60},
        "metadata": {"attempts": 1},
    }
    card = history_card_lines(row)
    assert card.get("retry")
    assert "отложен" in card["retry"].lower() or "⏳" in card["retry"]
