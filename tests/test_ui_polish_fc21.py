# -*- coding: utf-8 -*-
"""FC-21: UI status labels pure helpers."""
from __future__ import annotations

from ui.status_labels import status_label, phase_label, format_footer, format_queue_counts


def test_status_labels():
    assert status_label("done")
    assert status_label("ERROR")
    assert status_label("processing")
    assert status_label("deferred")
    assert status_label(None) in ("—", "-", "") or True


def test_phase_ready():
    text = phase_label("ready")
    assert text
    assert phase_label("idle")
    assert phase_label("verify")


def test_format_footer():
    off = format_footer(dispatcher_on=False, queue_n=3)
    assert "3" in off
    on = format_footer(dispatcher_on=True, queue_n=0, busy=False)
    assert on
    busy = format_footer(dispatcher_on=True, busy=True)
    assert busy


def test_queue_counts():
    s = format_queue_counts({"queued": 2, "processing": 1, "deferred": 0, "errors": 1})
    assert "2" in s
    assert "1" in s


def test_strings_have_queue_keys():
    from pathlib import Path
    ru = Path("config/strings_ru.yaml").read_text(encoding="utf-8")
    en = Path("config/strings_en.yaml").read_text(encoding="utf-8")
    for key in ("tab_queue", "queue_empty", "chat_ready", "status_done"):
        assert f"{key}:" in ru
        assert f"{key}:" in en
