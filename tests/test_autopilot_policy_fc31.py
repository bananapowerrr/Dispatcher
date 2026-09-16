# -*- coding: utf-8 -*-
"""FC-31 Autopilot Policy tests."""
from __future__ import annotations

from datetime import datetime

from intelligence.autopilot_policy import (
    ASK,
    AUTO,
    BLOCK,
    decide_emit_tasks,
    decide_for_conflict,
    decide_pipeline,
    resolve_mode,
)
from intelligence.conflict import ConflictRecord


def _c(risk: str = "MEDIUM", topic: str = "test_runner") -> ConflictRecord:
    return ConflictRecord(
        id="c1",
        topic=topic,
        current="a",
        new="b",
        recommendation="ask",
        risk=risk,
    )


def test_high_always_ask():
    d = decide_for_conflict(_c("HIGH", "database"), mode="full", autopilot_on=True)
    assert d.verdict == ASK
    assert "HIGH" in d.reason


def test_low_auto_balanced():
    d = decide_for_conflict(_c("LOW"), mode="balanced", autopilot_on=True)
    assert d.verdict == AUTO


def test_medium_cautious_asks():
    d = decide_for_conflict(_c("MEDIUM"), mode="cautious", autopilot_on=True)
    assert d.verdict == ASK


def test_flag_off_blocks_emit():
    d = decide_emit_tasks(autopilot_on=False, mode="full")
    assert d.verdict == BLOCK


def test_mode_off_asks_on_conflict():
    d = decide_for_conflict(_c("LOW"), mode="off", autopilot_on=True)
    assert d.verdict == ASK


def test_pipeline_one_high():
    d = decide_pipeline([_c("LOW"), _c("HIGH", "auth")], mode="full", now=datetime(2026, 1, 1, 12))
    assert d.verdict == ASK


def test_pipeline_all_low():
    d = decide_pipeline([_c("LOW"), _c("LOW")], mode="balanced")
    assert d.verdict == AUTO


def test_resolve_mode_env(monkeypatch):
    monkeypatch.setenv("AGENTBUS_AUTOPILOT_MODE", "night_full")
    assert resolve_mode() == "night_full"


def test_format_human():
    d = decide_for_conflict(_c("HIGH"), mode="balanced", autopilot_on=True)
    text = d.format_human()
    assert "ASK" in text and "HIGH" in text
