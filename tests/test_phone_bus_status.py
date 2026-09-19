"""Phone bus status helpers offline."""
from __future__ import annotations

from pathlib import Path

from ui.phone_bus_status import channel_counts, format_channel_status


def test_format_disabled_no_channels():
    text = format_channel_status({}, enabled=False)
    assert "Выключен" in text


def test_format_with_counts(tmp_path: Path):
    ch = tmp_path / "channels" / "gpt"
    (ch / "incoming").mkdir(parents=True)
    (ch / "incoming" / "a.json").write_text("{}", encoding="utf-8")
    (ch / "done").mkdir(parents=True)
    counts = channel_counts(tmp_path)
    assert counts["gpt"]["incoming"] == 1
    text = format_channel_status(counts, enabled=True)
    assert "Включён" in text
    assert "in=1" in text
