# -*- coding: utf-8 -*-
from __future__ import annotations

from utils.cost_tracker import CostTracker
from utils.pipeline_events import task_done, diff_policy
from eventbus import BUS, reset_bus


def test_cost_record_signature():
    t = CostTracker()
    r = t.record("tid-1", worker="ollama", provider="ollama", tokens_total=500)
    assert r.task_id == "tid-1"
    assert r.tokens_in + r.tokens_out == 500


def test_done_and_diff_events():
    reset_bus()
    seen = []
    BUS.attach(lambda e: seen.append(e.type))
    task_done("t9", "w1", duration=1.5, commit="abc")
    diff_policy("t9", {"risk": "MEDIUM", "action": "queue"})
    assert "TASK_DONE" in seen
    assert "DIFF_POLICY" in seen
