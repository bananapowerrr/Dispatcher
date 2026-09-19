"""Terminal line format without GUI."""
from __future__ import annotations

from ui.terminal_panel import format_term_line


def test_format_contains_source_and_msg():
    line = format_term_line("dispatcher", "START ok", ts="12:00:00")
    assert "[12:00:00]" in line
    assert "dispatcher" in line
    assert "START ok" in line
    assert line.endswith("\n")


def test_format_default_source():
    line = format_term_line("", "hello", ts="01:02:03")
    assert "system" in line
