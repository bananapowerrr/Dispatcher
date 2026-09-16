# -*- coding: utf-8 -*-
from pathlib import Path

from pev_loop import (
    heuristic_plan,
    write_plan,
    enrich_message_with_plan,
    verify_retry_message,
    should_use_pev,
)
from meta_classifier import _parse_meta_json


def test_should_use_pev_threshold(monkeypatch):
    monkeypatch.setenv("AGENTBUS_PEV", "1")
    monkeypatch.setenv("AGENTBUS_PEV_MIN_CX", "4")
    assert should_use_pev(4)
    assert not should_use_pev(2)


def test_heuristic_plan_rename(tmp_path: Path):
    plan = heuristic_plan("id1", "переименуй old_fn в new_fn", ["a.py"])
    assert plan.files == ["a.py"]
    assert any("rename" in s.action for s in plan.steps)
    path = write_plan(tmp_path, plan)
    assert path.is_file()
    assert "PLAN" in enrich_message_with_plan("do work", plan)


def test_verify_retry_appends_error():
    m = verify_retry_message("msg", "AssertionError: boom", 2)
    assert "VERIFY FAILED" in m
    assert "boom" in m


def test_meta_parse_fenced_json():
    obj = _parse_meta_json(
        'Here you go:\n```json\n{"task_type": "refactor", "complexity": 4, "summary": "x"}\n```'
    )
    assert obj is not None
    assert obj["task_type"] == "refactor"
    assert int(obj["complexity"]) == 4
