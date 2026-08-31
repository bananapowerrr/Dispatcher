# -*- coding: utf-8 -*-
"""P0: EventBus / Observability. emit не бросает, sinks пишут в JSONL."""
from __future__ import annotations
import json
import os

import pytest

from eventbus import EventBus, AgentEvent, JsonlSink, ConsoleSink, reset_bus
from eventbus.events import EVENT_TYPES, LIFECYCLE, AGENT, EXECUTION, HEALTH, SYSTEM


@pytest.fixture
def bus():
    b = EventBus()
    return b


# ---------- типы событий ----------
def test_event_types_are_defined():
    assert "CLAIM" in LIFECYCLE
    assert "THINKING" in AGENT
    assert "TOOL_CALL" in AGENT
    assert "TEST_START" in EXECUTION
    assert "COMMIT" in EXECUTION
    assert "HEARTBEAT" in HEALTH
    assert "QUEUE" in SYSTEM
    assert LIFECYCLE & EXECUTION == set()  # группы не пересекаются


def test_unknown_type_coerced_to_message():
    e = AgentEvent(type="BOGUS")
    assert e.type == "MESSAGE"


# ---------- emit / подписка / отписка ----------
def test_emit_delivers_to_listener(bus):
    got = []
    detach = bus.attach(lambda ev: got.append(ev))
    e = bus.emit(AgentEvent(type="START", task_id="t1", worker="w1"))
    assert got == [e]
    assert bus.count == 1
    detach()
    bus.emit(AgentEvent(type="DONE", task_id="t1"))
    assert len(got) == 1  # отписка сработала


def test_kwargs_build_event(bus):
    got = []
    bus.attach(lambda ev: got.append(ev))
    bus.emit(type="THINKING", task_id="t1", worker="w1", message="analysing")
    e = got[0]
    assert e.type == "THINKING"
    assert e.message == "analysing"
    assert e.task_id == "t1"


def test_emit_never_raises_on_bad_listener(bus):
    def bad(ev):
        raise RuntimeError("consumer boom")
    bus.attach(bad)
    got = []
    bus.attach(lambda ev: got.append(ev))
    bus.emit(AgentEvent(type="HEARTBEAT"))  # не должно упасть
    assert len(got) == 1  # остальные consumers продолжают


# ---------- JSONL sink ----------
def test_jsonl_writes_persistable_lines(tmp_path):
    inferred = reset_bus()
    sink = JsonlSink(tmp_path)
    inferred.attach(sink)
    inferred.emit(AgentEvent(type="START", task_id="t1", worker="w1",
                             executor="opencode", provider="groq", model="m"))
    inferred.emit(AgentEvent(type="DONE", task_id="t1", worker="w1", duration=2.5))
    sink.close()
    day = os.path.basename(list(tmp_path.iterdir())[0])
    lines = [json.loads(l) for l in (tmp_path / day).read_text(encoding="utf-8").splitlines()]
    assert lines[0]["type"] == "START"
    assert lines[0]["provider"] == "groq"
    assert lines[1]["type"] == "DONE"
    assert lines[1]["duration"] == 2.5
    assert "_ts_iso" in lines[0]


def test_jsonl_disabled_writes_nothing(tmp_path):
    inferred = reset_bus()
    sink = JsonlSink(tmp_path, enabled=False)
    inferred.attach(sink)
    inferred.emit(AgentEvent(type="DONE"))
    sink.close()
    assert not any(tmp_path.iterdir())


# ---------- console sink не падает ----------
def test_console_sink_does_not_raise(capsys):
    inferred = reset_bus()
    sink = ConsoleSink(enabled=True, refresh=1000)
    inferred.attach(sink)
    inferred.emit(AgentEvent(type="START", task_id="t1", worker="w1", message="go"))
    inferred.detach_all()
    captured = capsys.readouterr()
    assert "START" in captured.out


def test_console_sink_can_be_disabled():
    inferred = reset_bus()
    sink = ConsoleSink(enabled=False)
    inferred.attach(sink)
    inferred.emit(AgentEvent(type="DONE", message="x"))
    inferred.detach_all()
