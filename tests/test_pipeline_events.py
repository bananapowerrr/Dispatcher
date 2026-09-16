# -*- coding: utf-8 -*-
from __future__ import annotations

from eventbus import BUS, reset_bus, EVENT_TYPES
from utils import pipeline_events as pe


def test_new_event_types_registered():
    for t in ("TASK_CLAIMED", "WORKER_SELECTED", "VERIFY_PASSED", "SKILL_HIT", "DIFF_POLICY"):
        assert t in EVENT_TYPES


def test_pipeline_helpers_emit():
    reset_bus()
    seen = []
    BUS.attach(lambda e: seen.append(e.type))
    pe.task_claimed("t1", worker="w")
    pe.worker_selected("t1", "w", score=1.2)
    pe.verify_started("t1", "w")
    pe.verify_passed("t1", "w")
    pe.skill_hit("t1", "format_code")
    pe.cache_hit("t1")
    pe.diff_policy("t1", {"risk": "LOW", "action": "auto"})
    pe.task_done("t1", "w", duration=1.0)
    assert "TASK_CLAIMED" in seen
    assert "WORKER_SELECTED" in seen
    assert "SKILL_HIT" in seen
    assert BUS.count >= 7
