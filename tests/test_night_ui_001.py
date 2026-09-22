# -*- coding: utf-8 -*-
from pathlib import Path


def test_status_line():
    from ui.night_notice import format_night_status_line, night_status_snapshot

    snap = night_status_snapshot()
    line = format_night_status_line(snap)
    assert "Night Mode" in line
    assert "parallel=1" in line


def test_morning_report_empty():
    from ui.night_notice import build_morning_report_text, morning_report_from_last_run

    text = build_morning_report_text(session={"done": ["s0"], "errors": [], "stopped_reason": "complete"})
    assert "Morning Report" in text or "DONE" in text or "done" in text.lower()
    # no crash
    morning_report_from_last_run()


def test_settings_has_night_tab():
    src = Path("/home/workdir/artifacts/ui/settings_panel.py").read_text(encoding="utf-8")
    assert "_build_night_tab" in src
    assert "morning_report_from_last_run" in src


def test_chat_has_night_notice():
    src = Path("/home/workdir/artifacts/ui/chat_panel.py").read_text(encoding="utf-8")
    assert "_maybe_notify_night" in src
