"""Composer validation helpers offline."""
from __future__ import annotations

import pytest

from app.task_composer import compose_task, validate_task_dict, format_composer_preview


def test_compose_minimal():
    t = compose_task(message="fix bug", project="/tmp/p", channel="desktop")
    assert t.get("message") == "fix bug"
    assert isinstance(validate_task_dict(t), list)


def test_compose_empty_message_raises():
    with pytest.raises(ValueError):
        compose_task(message="  ", project="/tmp/p")


def test_preview_nonempty():
    t = compose_task(message="add tests", files=["a.py"])
    text = format_composer_preview(t)
    assert len(text) > 0
