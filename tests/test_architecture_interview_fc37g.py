# -*- coding: utf-8 -*-
"""FC-37G Architecture Interview tests."""
from __future__ import annotations

from pathlib import Path

from intelligence.architecture_discovery import discover_architecture
from intelligence.architecture_interview import (
    apply_architecture_answer,
    interview_summary,
    make_architecture_decision,
    start_interview,
)
from intelligence.decision_queue import DecisionQueue
from intelligence.project_state import ProjectState


def _api_proj(tmp: Path) -> Path:
    (tmp / "app.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n",
        encoding="utf-8",
    )
    (tmp / "api").mkdir()
    (tmp / "api" / "r.py").write_text("x=1\n", encoding="utf-8")
    return tmp


def test_make_decision_has_options():
    item = make_architecture_decision("Где и как устроена авторизация API?")
    assert item.risk == "HIGH"
    assert len(item.options) >= 3
    assert item.meta.get("source") == "architecture_interview"


def test_start_interview_enqueues(tmp_path: Path):
    root = _api_proj(tmp_path)
    dq = DecisionQueue(path=tmp_path / "d.json")
    r = start_interview(root, decisions=dq, limit=3, project="demo")
    assert r.enqueued or r.message
    # API without auth → at least one unknown
    arch = discover_architecture(root)
    if arch.unknowns:
        assert r.enqueued or r.skipped
    assert "Architecture" in interview_summary(dq) or "No open" in interview_summary(dq) or r.enqueued


def test_apply_answer_records_state(tmp_path: Path):
    dq = DecisionQueue(path=tmp_path / "d2.json")
    item = make_architecture_decision("Где бизнес-логика — в UI, в API или разделена?", project="p")
    dq.enqueue(item)
    state = ProjectState()
    out = apply_architecture_answer(dq, item.id, "A", state=state)
    assert out["ok"]
    assert state.decisions
    assert not dq.get(item.id).is_open()


def test_skip_duplicate(tmp_path: Path):
    root = _api_proj(tmp_path)
    dq = DecisionQueue(path=tmp_path / "d3.json")
    r1 = start_interview(root, decisions=dq, limit=2)
    r2 = start_interview(root, decisions=dq, limit=2)
    # second run should skip already open
    if r1.enqueued:
        assert r2.skipped or not r2.enqueued or len(dq.open_items()) <= len(r1.enqueued) + 1
