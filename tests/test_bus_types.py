# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from bus import FileBus, STATES


def test_filebus_write_move(tmp_path: Path) -> None:
    bus = FileBus(tmp_path, ("gpt",))
    bus.ensure()
    p = bus.write("gpt", "incoming", "t1.json", '{"ok":1}')
    assert p.is_file()
    assert bus.move("gpt", "incoming", "processing", "t1.json") is True
    assert not (tmp_path / "channels" / "gpt" / "incoming" / "t1.json").exists()
    assert (tmp_path / "channels" / "gpt" / "processing" / "t1.json").is_file()
    # second move of missing → False
    assert bus.move("gpt", "incoming", "processing", "t1.json") is False


def test_states_tuple() -> None:
    assert "incoming" in STATES and "done" in STATES
