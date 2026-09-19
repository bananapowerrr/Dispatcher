"""Metrics board empty paths offline."""
from __future__ import annotations

from ui.metrics_panel import format_metrics_board


def test_empty_metrics_mentions_dispatcher():
    text = format_metrics_board(
        {},
        {"desktop": 0, "incoming": 0, "processing": 0, "done": 0, "errors": 0, "deferred": 0},
    )
    assert "Очередь" in text
    assert "metrics_latest" in text or "dispatcher" in text.lower()
    assert "нет" in text or "пусто" in text or "пока" in text


def test_queue_line_present():
    text = format_metrics_board(
        {},
        {"desktop": 2, "incoming": 1, "processing": 0, "done": 3, "errors": 0, "deferred": 0},
    )
    assert "desktop" in text
    assert "in:1" in text
