# -*- coding: utf-8 -*-
"""Strict Task.transition state machine."""
from __future__ import annotations

import pytest

from core.tasks import Task, STATES, TRANSITIONS


def _task(status: str = "PENDING") -> Task:
    t = Task(
        id="t1",
        project="/tmp/p",
        message="hi",
        files=[],
        channel="desktop",
        status=status,
    )
    return t


def test_states_include_processing_verifying():
    assert "PROCESSING" in STATES
    assert "VERIFYING" in STATES
    assert "DONE" in STATES


@pytest.mark.parametrize(
    "src,dst",
    [
        ("PENDING", "CLAIMED"),
        ("CLAIMED", "PROCESSING"),
        ("CLAIMED", "DONE"),
        ("CLAIMED", "ERROR"),
        ("CLAIMED", "DEFERRED"),
        ("PROCESSING", "VERIFYING"),
        ("PROCESSING", "DONE"),
        ("PROCESSING", "ERROR"),
        ("VERIFYING", "DONE"),
        ("VERIFYING", "ERROR"),
        ("DEFERRED", "CLAIMED"),
        ("ERROR", "CLAIMED"),
    ],
)
def test_allowed(src, dst):
    t = _task(src)
    t.transition(dst)
    assert t.status == dst


@pytest.mark.parametrize(
    "src,dst",
    [
        ("DONE", "PENDING"),
        ("DONE", "CLAIMED"),
        ("DONE", "ERROR"),
        ("DONE", "PROCESSING"),
        ("ERROR", "DONE"),
        ("PENDING", "DONE"),
        ("PENDING", "ERROR"),
        ("DEFERRED", "DONE"),
    ],
)
def test_forbidden(src, dst):
    t = _task(src)
    with pytest.raises(ValueError, match="illegal transition|bad status"):
        t.transition(dst)


def test_retry_from_error():
    t = _task("ERROR")
    t.retry()
    assert t.status == "CLAIMED"


def test_retry_from_done_fails():
    t = _task("DONE")
    with pytest.raises(ValueError):
        t.retry()


def test_done_is_terminal():
    assert TRANSITIONS["DONE"] == frozenset()
