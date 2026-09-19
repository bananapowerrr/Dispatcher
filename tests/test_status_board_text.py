"""Status board pure text offline."""
from __future__ import annotations

from pathlib import Path

from utils.status_board import format_board_text, channel_snapshot, safety_flags


def test_safety_flags_keys():
    f = safety_flags()
    assert "syntax_guard" in f
    assert "max_parallel_projects" in f


def test_format_board_empty_root(tmp_path: Path):
    text = format_board_text(tmp_path, channels=("gpt",))
    assert "status board" in text
    assert "safety:" in text
    assert "gpt" in text or "queues" in text


def test_channel_snapshot_counts(tmp_path: Path):
    inc = tmp_path / "channels" / "gpt" / "incoming"
    inc.mkdir(parents=True)
    (inc / "a.json").write_text("{}", encoding="utf-8")
    rows = channel_snapshot(tmp_path, ["gpt"])
    assert rows[0]["incoming"] == 1
