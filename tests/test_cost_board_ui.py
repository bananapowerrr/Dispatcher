# -*- coding: utf-8 -*-
"""Offline: cost board text without GUI toolkit."""


def test_cost_tracker_snapshot_dict():
    from utils.cost_tracker import CostTracker, CostSnapshot
    snap = CostSnapshot(session_cost_usd=0.0, skill_saves=2, cache_saves=1)
    d = snap.to_dict()
    assert d["session_cost_usd"] == 0.0
    assert d["skill_saves"] == 2


def test_cost_board_format_logic():
    data = {
        "session_tokens_in": 10,
        "session_tokens_out": 20,
        "session_cost_usd": 0.0,
        "calls": 0,
        "skill_saves": 3,
        "cache_saves": 2,
    }
    usd = float(data.get("session_cost_usd") or 0)
    assert usd <= 0
    line = f"local share   : skills={data['skill_saves']}  cache={data['cache_saves']}"
    assert "skills=3" in line
