"""Plan / Task Detail empty offline."""
from __future__ import annotations

from ui.plan_hints import plan_empty_text
from ui.task_detail_hints import task_detail_empty_text


def test_plan_no_project():
    t = plan_empty_text(has_project=False)
    assert "проект" in t.lower() or "Setup" in t


def test_plan_no_steps():
    t = plan_empty_text(has_project=True, has_steps=False)
    assert "+" in t or "шаг" in t.lower() or "Advisor" in t


def test_task_detail_empty():
    t = task_detail_empty_text()
    assert "Queue" in t or "History" in t
    assert "trace" in t.lower() or "FSM" in t or "lifecycle" in t.lower()
