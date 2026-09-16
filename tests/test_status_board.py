# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


def test_channel_snapshot_counts(tmp_path: Path):
    from utils.status_board import channel_snapshot, board_dict

    ch = tmp_path / "channels" / "gpt"
    for stage in ("incoming", "processing", "done", "errors", "deferred"):
        d = ch / stage
        d.mkdir(parents=True)
    (ch / "incoming" / "a.json").write_text("{}", encoding="utf-8")
    (ch / "incoming" / "b.json").write_text("{}", encoding="utf-8")
    (ch / "processing" / "c.json").write_text("{}", encoding="utf-8")
    rows = channel_snapshot(tmp_path, ["gpt"])
    assert rows[0]["incoming"] == 2
    assert rows[0]["processing"] == 1
    d = board_dict(tmp_path)
    assert "flags" in d
    assert d["flags"]["max_parallel_projects"] in ("1", "2") or d["flags"]["max_parallel_projects"]


def test_print_board_no_crash(tmp_path: Path, capsys):
    from utils.status_board import print_board

    (tmp_path / "channels" / "gpt" / "incoming").mkdir(parents=True)
    print_board(tmp_path, ["gpt"])
    out = capsys.readouterr().out
    assert "status board" in out
    assert "gpt" in out
