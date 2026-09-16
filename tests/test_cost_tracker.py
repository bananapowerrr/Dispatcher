# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from utils.cost_tracker import CostTracker, GLOBAL_COST


def test_local_zero_cost():
    t = CostTracker()
    r = t.record("t1", worker="ollama", provider="ollama", tokens_in=1000, tokens_out=500)
    assert r.usd == 0.0
    assert r.local is True


def test_cloud_cost_positive():
    t = CostTracker()
    r = t.record("t2", provider="openai", tokens_in=1_000_000, tokens_out=0)
    assert r.usd > 0
    snap = t.snapshot()
    assert snap["session_usd"] > 0
    assert snap["tasks"] == 1


def test_persist_jsonl(tmp_path: Path):
    path = tmp_path / "costs.jsonl"
    t = CostTracker(path=path)
    t.record("t3", provider="local", tokens_total=100)
    assert path.is_file()
    line = path.read_text(encoding="utf-8").strip()
    assert "t3" in line


def test_autopilot_goal_graph(tmp_path: Path):
    from skills.autopilot import Autopilot
    # minimal project
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x=1\n", encoding="utf-8")
    ap = Autopilot(str(tmp_path))
    ids = ap.emit_goal_graph(
        ["analyze structure", "fix issues"],
        bus_root=tmp_path,
        channel="autopilot",
        max_emit=1,
    )
    assert ids
    incoming = list((tmp_path / "channels" / "autopilot" / "incoming").glob("*.json"))
    assert incoming
