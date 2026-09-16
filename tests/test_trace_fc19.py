# -*- coding: utf-8 -*-
"""FC-19: TaskTrace product timeline."""
from __future__ import annotations

from utils.task_trace import (
    GLOBAL_TRACES,
    TaskTrace,
    event_label,
    timeline_from_any,
    format_trace_for_ui,
)
from core.task_result import build_task_result, history_card_lines


def test_event_labels():
    assert "старт" in event_label("TASK_STARTED")
    assert "готово" in event_label("DONE")
    assert "навык" in event_label("SKILL")


def test_timeline_from_events_dict():
    raw = {
        "events": [
            {"name": "TASK_STARTED", "detail": {}},
            {"name": "SKILL", "detail": {"skill": "format_code"}},
            {"name": "VERIFY", "detail": {}},
            {"name": "DONE", "detail": {}},
        ]
    }
    lines = timeline_from_any(raw)
    assert any("старт" in x for x in lines)
    assert any("навык" in x for x in lines)
    assert any("готово" in x for x in lines)


def test_task_trace_format_human():
    tr = GLOBAL_TRACES.start("tid-fc19", worker_id="aider", attempt=1)
    tr.add("SKILL", skill="format_code")
    tr.add("VERIFY")
    GLOBAL_TRACES.complete("tid-fc19", "DONE")
    finished = GLOBAL_TRACES._finished["tid-fc19"]
    text = finished.format_human()
    assert "DONE" in text or "готово" in text
    assert "format" in text.lower() or "навык" in text


def test_build_task_result_timeline():
    row = {
        "id": "t1",
        "status": "DONE",
        "message": "x",
        "metadata": {
            "trace": {
                "events": [
                    {"name": "TASK_STARTED"},
                    {"name": "WORKER", "detail": {"worker": "aider"}},
                    {"name": "DONE"},
                ]
            }
        },
        "result": {"ok": True, "worker": "aider"},
    }
    tr = build_task_result(row)
    assert tr.timeline
    assert any("старт" in s or "воркер" in s or "готово" in s for s in tr.timeline)
    card = history_card_lines(row)
    assert card.get("trace")


def test_format_trace_for_ui_from_store():
    GLOBAL_TRACES.start("tid-ui", worker_id="ollama")
    GLOBAL_TRACES.complete("tid-ui", "ERROR")
    text = format_trace_for_ui("tid-ui")
    assert "tid-ui" in text or "ERROR" in text or "ошибка" in text
