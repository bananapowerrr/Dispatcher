# -*- coding: utf-8 -*-
"""Day 18: live failure layer classifier."""
from __future__ import annotations

from core.live_fail_layer import (
    classify_error_text,
    classify_task_row,
    format_classification,
    layer_hint,
)


def test_classify_env():
    assert classify_error_text("Ollama not reachable at 127.0.0.1:11434") == "ENV"
    assert classify_error_text("aider: command not found") == "ENV"


def test_classify_verify():
    assert classify_error_text("verification failed: syntax error") == "VERIFY"
    assert classify_error_text("pytest collected 0 / tests failed") == "VERIFY"


def test_classify_worker():
    assert classify_error_text("no worker available; primary: (none)") == "WORKER"
    assert classify_error_text("live coding stack NOT READY") == "WORKER"


def test_classify_plan():
    assert classify_error_text("plan step IN_PROGRESS blocks enqueue") == "PLAN"


def test_classify_task_row():
    row = {
        "id": "t1",
        "status": "error",
        "result": {"error": "verify failed: empty diff", "worker": "aider_local"},
    }
    out = classify_task_row(row)
    assert out["layer"] == "VERIFY"
    assert out["task_id"] == "t1"
    assert "Hint:" in format_classification(out)


def test_layer_hint_known():
    assert "Ollama" in layer_hint("ENV")
    assert "claim" in layer_hint("RUNTIME").lower() or "queue" in layer_hint("RUNTIME").lower()


def test_unknown():
    assert classify_error_text("something weird xyz") == "UNKNOWN"
