# -*- coding: utf-8 -*-
import json
from pathlib import Path

from bus import FileBus


def test_filebus_allows_sub_channel(tmp_path):
    bus = FileBus(tmp_path, ("gpt",))
    paths = bus.paths("gpt__sub_parent1")
    assert paths["incoming"] == tmp_path / "channels" / "gpt__sub_parent1" / "incoming"
    bus.write(
        "gpt__sub_parent1",
        "incoming",
        "t1.json",
        json.dumps({"id": "t1", "message": "hi"}),
    )
    assert (paths["incoming"] / "t1.json").is_file()


def test_filebus_rejects_unknown_non_sub(tmp_path):
    bus = FileBus(tmp_path, ("gpt",))
    try:
        bus.paths("random_channel")
        assert False, "should raise"
    except ValueError:
        pass


def test_discover_sub_dirs(tmp_path):
    """Mirror _active_channels discovery without importing heavy runtime."""
    ch_root = tmp_path / "channels"
    (ch_root / "gpt" / "incoming").mkdir(parents=True)
    (ch_root / "gpt__sub_abc" / "incoming").mkdir(parents=True)
    base = ["gpt", "grok"]
    found = list(base)
    seen = set(base)
    for d in sorted(ch_root.iterdir()):
        if d.is_dir() and "__sub_" in d.name and d.name not in seen:
            found.append(d.name)
            seen.add(d.name)
    assert "gpt__sub_abc" in found
