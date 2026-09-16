# -*- coding: utf-8 -*-
"""FC-28 Context Intake classification."""
from __future__ import annotations

from intelligence.context_intake import (
    COMMAND, CONSTRAINT, DECISION, EVIDENCE, GOAL, INFORMATION, QUESTION,
    classify_message, apply_intake_to_state,
)
from intelligence.project_state import load_project_state


def test_command():
    r = classify_message("добавь type hints в src/core/bus.py")
    assert r.kind == COMMAND
    assert r.should_create_task


def test_question():
    r = classify_message("Как работает file-bus?")
    assert r.kind == QUESTION
    assert not r.should_create_task


def test_constraint():
    r = classify_message("Нельзя использовать cloud API, только локально")
    assert r.kind == CONSTRAINT
    assert r.should_update_state


def test_decision_replan():
    r = classify_message("Решаем: вместо SQLite переходим на PostgreSQL")
    assert r.kind in (DECISION, CONSTRAINT, COMMAND)
    assert r.should_replan or r.kind == DECISION


def test_evidence_traceback():
    r = classify_message("Traceback (most recent call last):\n  File \"a.py\"\nAssertionError: fail")
    assert r.kind == EVIDENCE


def test_goal():
    r = classify_message("Цель: сделать AgentBus массовым продуктом для РФ")
    assert r.kind == GOAL


def test_apply_constraint_state(tmp_path):
    r = classify_message("Запрещено ходить в интернет без явного разрешения")
    assert r.kind == CONSTRAINT
    acts = apply_intake_to_state(r, project_root=str(tmp_path))
    assert "constraint" in acts
    st = load_project_state(tmp_path)
    assert st.constraints


def test_info_note(tmp_path):
    r = classify_message("Кстати, в этом проекте тесты запускаются через poetry run pytest")
    assert r.kind in (INFORMATION, CONSTRAINT, COMMAND)
    apply_intake_to_state(r, project_root=str(tmp_path))
