# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from intelligence.sub_agent import SubAgent, MAX_DEPTH
from intelligence.task_graph import TaskGraph, emit_ready_to_bus


def test_spawn_blocked_at_max_depth(tmp_path: Path):
    bus = tmp_path
    sa = SubAgent(bus, channel="gpt")
    # depth already at MAX_DEPTH
    r = sa.spawn_many(
        [{"message": "child work", "files": []}],
        parent_id="p1",
        parent_depth=MAX_DEPTH,
        max_children=3,
    )
    assert r.task_ids == []


def test_spawn_sets_sub_depth(tmp_path: Path):
    sa = SubAgent(tmp_path, channel="gpt")
    r = sa.spawn_many(
        [{"message": "do a", "files": ["a.py"]}],
        parent_id="parent",
        parent_depth=0,
        max_children=2,
    )
    assert len(r.task_ids) == 1
    # read written json
    files = list((tmp_path / "channels").rglob("sub_*.json"))
    assert files
    import json
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["metadata"]["sub_depth"] == 1
    assert data["metadata"]["is_subtask"] is True


def test_task_graph_linear_ready():
    g = TaskGraph.from_goal_steps(["explore", "implement", "test"])
    ready = g.ready()
    assert len(ready) == 1
    assert "explore" in ready[0].message
    g.mark(ready[0].id, "DONE")
    ready2 = g.ready()
    assert len(ready2) == 1
    assert "implement" in ready2[0].message


def test_emit_ready(tmp_path: Path):
    g = TaskGraph.from_goal_steps(["step one"])
    ids = emit_ready_to_bus(g, bus_root=tmp_path, channel="autopilot", parent_id="goal1")
    assert ids
    assert (tmp_path / "channels" / "autopilot" / "incoming" / f"{ids[0]}.json").is_file()
