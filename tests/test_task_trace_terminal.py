# -*- coding: utf-8 -*-
"""P0-2: every terminal path closes TaskTrace."""
from __future__ import annotations

from utils.task_trace import (
    GLOBAL_TRACES,
    TraceStore,
    complete_task_trace,
    is_terminal_event,
    normalize_terminal,
)


def test_normalize_terminal():
    assert normalize_terminal("done") == "DONE"
    assert normalize_terminal("TASK_ERROR") == "ERROR"
    assert normalize_terminal("CANCEL") == "CANCELLED"


def test_is_terminal():
    assert is_terminal_event("DONE")
    assert is_terminal_event("RETRY")
    assert is_terminal_event("DEFERRED")
    assert not is_terminal_event("HEARTBEAT")


def test_complete_task_trace_lifecycle(tmp_path):
    store = TraceStore(path=tmp_path / "t.jsonl")
    # temporarily use isolated store
    import utils.task_trace as tt
    old = tt.GLOBAL_TRACES
    tt.GLOBAL_TRACES = store
    try:
        store.start("t1", project_id="p", attempt=1, worker_id="w")
        store.get("t1").add("WORKER_STARTED")
        tr = complete_task_trace("t1", "DONE", note="ok")
        assert tr is not None
        assert tr.final_status == "DONE"
        assert any(e.name == "TASK_STARTED" for e in tr.events)
        assert tr.duration() >= 0
        # second complete is idempotent
        tr2 = complete_task_trace("t1", "ERROR")
        assert tr2 is not None
        assert tr2.final_status == "DONE"  # first terminal wins
    finally:
        tt.GLOBAL_TRACES = old


def test_all_terminal_statuses(tmp_path):
    store = TraceStore(path=tmp_path / "t2.jsonl")
    import utils.task_trace as tt
    old = tt.GLOBAL_TRACES
    tt.GLOBAL_TRACES = store
    try:
        for i, st in enumerate(["DONE", "ERROR", "RETRY", "DEFERRED", "CANCELLED"]):
            tid = f"x{i}"
            store.start(tid, attempt=1)
            tr = complete_task_trace(tid, st)
            assert tr is not None
            assert tr.final_status == st
            assert tr.task_id == tid
    finally:
        tt.GLOBAL_TRACES = old


def test_emit_path_helper_closes_trace():
    """Mirror Runtime._emit terminal handling without full Runtime init."""
    import utils.task_trace as tt
    store = TraceStore()
    old = tt.GLOBAL_TRACES
    tt.GLOBAL_TRACES = store
    try:
        store.start("emit1", attempt=2)
        assert is_terminal_event("ERROR")
        tr = complete_task_trace("emit1", "ERROR", message="fail")
        assert tr is not None and tr.final_status == "ERROR"
        assert store.get("emit1") is None
        # idempotent
        tr2 = complete_task_trace("emit1", "DONE")
        assert tr2 is not None and tr2.final_status == "ERROR"
    finally:
        tt.GLOBAL_TRACES = old
