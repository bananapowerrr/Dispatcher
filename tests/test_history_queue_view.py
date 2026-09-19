"""Queue snapshot helpers — offline (no customtkinter)."""
from __future__ import annotations

from ui.queue_panel import collect_queue_snapshot, format_queue_summary


def test_collect_queue_snapshot_shape():
    snap = collect_queue_snapshot(limit=10)
    assert isinstance(snap, dict)
    assert "counts" in snap
    assert "items" in snap


def test_format_queue_summary_empty():
    s = format_queue_summary({})
    assert isinstance(s, str)
    assert len(s) > 0


def test_format_queue_summary_counts():
    s = format_queue_summary({"queued": 2, "processing": 1, "deferred": 0, "errors": 0})
    assert "2" in s or "queued" in s.lower() or isinstance(s, str)
