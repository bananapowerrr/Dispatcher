"""Metrics board text without GUI."""
from __future__ import annotations

from ui.metrics_panel import format_metrics_board, _bar


def test_bar_basic():
    s = _bar("cache", 0.5)
    assert "cache" in s


def test_board_empty_metrics():
    text = format_metrics_board({}, {"desktop": 1, "incoming": 0, "processing": 0, "done": 0, "errors": 0, "deferred": 0})
    assert "Очередь" in text
    assert "desktop" in text
    assert "metrics_latest" in text or "dispatcher" in text.lower() or "snapshot" in text.lower()


def test_board_with_rates():
    m = {
        "hit_rates": {"cache_hit_rate": 0.4, "skill_hit_rate": 0.2, "llm_success_rate": 0.9, "cache_total": 10, "skill_total": 5},
        "counters": {"cache_hit": 4, "skill_hit": 1},
    }
    text = format_metrics_board(m, {"desktop": 0, "incoming": 0, "processing": 0, "done": 2, "errors": 0, "deferred": 0})
    assert "Hit rates" in text
    assert "cache" in text.lower()
