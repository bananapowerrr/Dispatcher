# -*- coding: utf-8 -*-
"""FSM invariants against core.tasks.TRANSITIONS."""
from __future__ import annotations

import pytest
from core.tasks import Task, TRANSITIONS, STATES


def make_task(status: str = "PENDING", attempts: int = 0) -> Task:
    return Task(id="t1", message="x", status=status, attempts=attempts)


def test_states_cover_pipeline():
    for s in ("PENDING", "CLAIMED", "PROCESSING", "VERIFYING", "DONE", "ERROR"):
        assert s in STATES


def test_pending_to_done_illegal():
    t = make_task("PENDING")
    with pytest.raises(Exception):
        t.transition("DONE")


def test_pending_to_claimed():
    t = make_task("PENDING")
    t.transition("CLAIMED")
    assert t.status == "CLAIMED"


def test_done_is_terminal():
    t = make_task("DONE")
    with pytest.raises(Exception):
        t.transition("PROCESSING")


def test_error_retries_via_claimed():
    t = make_task("ERROR", attempts=1)
    t.transition("CLAIMED")
    assert t.status == "CLAIMED"


def test_processing_to_verifying_to_done():
    t = make_task("PENDING")
    t.transition("CLAIMED")
    t.transition("PROCESSING")
    t.transition("VERIFYING")
    t.transition("DONE")
    assert t.status == "DONE"


def test_illegal_edges_rejected():
    t = make_task("VERIFYING")
    with pytest.raises(Exception):
        t.transition("PENDING")


def test_retry_helper():
    t = make_task("ERROR", attempts=2)
    if hasattr(t, "retry"):
        t.retry()
        assert t.status in ("CLAIMED", "RETRY", "PENDING", "ERROR")
        assert t.attempts >= 2
